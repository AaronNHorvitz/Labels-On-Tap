"""Job creation, upload processing, result pages, and CSV export routes.

Notes
-----
The sprint prototype uses a filesystem job store. Single uploads process
immediately; manifest-backed batch uploads write a durable local queue record
so the browser can redirect to a polling progress page while a local worker
writes results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image

from app.config import (
    JOBS_DIR,
    MAX_ARCHIVE_BYTES,
    MAX_BATCH_ITEMS,
    MAX_MANIFEST_BYTES,
    MAX_UPLOAD_BYTES,
    PUBLIC_COLA_DEMO_DIR,
    ROOT,
)
from app.schemas.application import ColaApplication
from app.schemas.manifest import ManifestItem
from app.schemas.ocr import OCRResult
from app.services.csv_export import results_to_csv
from app.services.batch_queue import enqueue_batch, load_queue_status
from app.services.cola_cloud_demo import (
    build_comparison_payload,
    load_cached_conveyor_ocr,
    load_cola_cloud_demo_source,
)
from app.services.job_store import (
    add_manifest_item,
    create_job,
    delete_job,
    job_dir,
    list_results,
    load_manifest,
    load_result,
    read_json,
    save_upload,
    write_result,
    write_json,
)
from app.services.manifest_parser import ManifestParseError, parse_manifest
from app.services.ocr.fixture_engine import FixtureOCREngine
from app.services.photo_intake import parse_photo_intake
from app.services.preflight.file_signature import (
    has_allowed_image_signature,
    is_pillow_decodable_image,
)
from app.services.preflight.upload_policy import (
    ALLOWED_IMAGE_EXTENSIONS,
    copy_upload_with_size_limit,
    random_upload_filename,
    read_upload_with_size_limit,
    validate_upload_name,
)
from app.services.rules.registry import verify_label
from app.services.rules.strict_warning import CANONICAL_WARNING
from app.services.typography.boldness import assess_warning_heading_boldness
from app.services.typography.warning_heading import detect_warning_heading_crop


router = APIRouter()
templates = Jinja2Templates(directory=str(ROOT / "app/templates"))
ocr_engine = FixtureOCREngine()


@dataclass
class ValidatedUpload:
    """Temporary upload metadata after preflight validation.

    Attributes
    ----------
    original_filename:
        User-provided filename preserved for UI display and CSV export.
    stored_filename:
        Randomized server-side filename used to avoid trusting user input.
    temp_path:
        Temporary path used before the upload is moved into a job directory.
    upload_size:
        Number of bytes copied after enforcing the configured size limit.
    """

    original_filename: str
    stored_filename: str
    temp_path: Path
    upload_size: int


def _validate_image_upload(upload: UploadFile, temp_dir: Path) -> ValidatedUpload:
    """Validate and stage one uploaded label image.

    Parameters
    ----------
    upload:
        FastAPI upload object for a user-supplied label image.
    temp_dir:
        Temporary directory owned by the current request.

    Returns
    -------
    ValidatedUpload
        Metadata for a staged upload that passed filename, size, signature, and
        Pillow decode checks.

    Raises
    ------
    HTTPException
        Raised with ``400`` for unsafe/invalid images and ``413`` for uploads
        exceeding ``MAX_UPLOAD_BYTES``.

    Notes
    -----
    The original filename is never used as the stored filename. It is kept only
    as display metadata so result pages remain understandable to reviewers.
    """

    return _validate_image_upload_with_policy(upload, temp_dir, allow_relative_name=False)


def _normalize_relative_upload_name(filename: str) -> str:
    """Return a safe relative upload key for application-folder matching."""

    normalized = filename.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.name or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Upload filename must be a safe relative path.")
    suffixes = [suffix.lower() for suffix in PurePosixPath(path.name).suffixes]
    if not suffixes or suffixes[-1] not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Unsupported label image type. Use JPG or PNG.")
    if len(suffixes) > 1:
        raise ValueError("Double-extension uploads are not accepted.")
    return path.as_posix()


def _validate_image_upload_with_policy(upload: UploadFile, temp_dir: Path, *, allow_relative_name: bool) -> ValidatedUpload:
    """Validate and stage an upload, optionally preserving a safe folder key."""

    if not upload.filename:
        raise HTTPException(status_code=400, detail="Missing upload filename")
    original_filename = upload.filename
    try:
        if allow_relative_name:
            original_filename = _normalize_relative_upload_name(original_filename)
        else:
            validate_upload_name(original_filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stored_filename = random_upload_filename(original_filename)
    temp_path = temp_dir / stored_filename
    try:
        upload_size = copy_upload_with_size_limit(upload.file, temp_path, MAX_UPLOAD_BYTES)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    if not has_allowed_image_signature(temp_path):
        raise HTTPException(status_code=400, detail=f"{original_filename}: upload does not match JPG/PNG signature")
    if not is_pillow_decodable_image(temp_path):
        raise HTTPException(status_code=400, detail=f"{original_filename}: upload is not a readable JPG/PNG image")

    return ValidatedUpload(
        original_filename=original_filename,
        stored_filename=stored_filename,
        temp_path=temp_path,
        upload_size=upload_size,
    )


def _safe_directory_key(filename: str) -> str:
    """Return a safe relative key for a directory-upload member."""

    normalized = filename.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.name or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Directory upload contains an unsafe path.")
    return path.as_posix()


def _strip_directory_root(filename: str, root_prefix: str) -> str:
    """Strip the selected browser directory prefix from an uploaded file key."""

    if root_prefix and filename.startswith(f"{root_prefix}/"):
        return filename[len(root_prefix) + 1 :]
    return filename


def _validate_image_bytes(original_filename: str, content: bytes, temp_dir: Path) -> ValidatedUpload:
    """Validate one in-memory image extracted from a ZIP archive."""

    try:
        original_filename = _normalize_relative_upload_name(original_filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{original_filename}: {exc}") from exc
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{original_filename}: upload exceeds maximum size of {MAX_UPLOAD_BYTES} bytes.")
    stored_filename = random_upload_filename(original_filename)
    temp_path = temp_dir / stored_filename
    temp_path.write_bytes(content)
    if not has_allowed_image_signature(temp_path):
        raise HTTPException(status_code=400, detail=f"{original_filename}: upload does not match JPG/PNG signature")
    if not is_pillow_decodable_image(temp_path):
        raise HTTPException(status_code=400, detail=f"{original_filename}: upload is not a readable JPG/PNG image")
    return ValidatedUpload(
        original_filename=original_filename,
        stored_filename=stored_filename,
        temp_path=temp_path,
        upload_size=len(content),
    )


def _validate_zip_upload(upload: UploadFile, temp_dir: Path) -> list[ValidatedUpload]:
    """Extract and validate JPG/PNG label images from one ZIP archive.

    The manifest still controls which images are used. ZIP paths are flattened
    to their basename so ``labels/front.png`` matches ``front.png`` in the
    manifest without trusting archive path components.
    """

    if not upload.filename:
        return []
    if Path(upload.filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Image archive must be a .zip file.")
    try:
        archive_content = read_upload_with_size_limit(upload.file, MAX_ARCHIVE_BYTES)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    try:
        archive = ZipFile(BytesIO(archive_content))
    except BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Image archive is not a valid ZIP file.") from exc

    uploads: list[ValidatedUpload] = []
    total_uncompressed = 0
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            original_filename = member.filename.replace("\\", "/").strip("/")
            if not original_filename:
                continue
            if PurePosixPath(original_filename).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
                continue
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_ARCHIVE_BYTES:
                raise HTTPException(status_code=413, detail=f"ZIP contents exceed maximum size of {MAX_ARCHIVE_BYTES} bytes.")
            if len(uploads) >= MAX_BATCH_ITEMS:
                raise HTTPException(status_code=400, detail=f"ZIP contains more than the maximum {MAX_BATCH_ITEMS} label images.")
            try:
                content = archive.read(member)
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=f"{original_filename}: could not read ZIP member.") from exc
            uploads.append(_validate_image_bytes(original_filename, content, temp_dir))
    if not uploads:
        raise HTTPException(status_code=400, detail="ZIP archive did not contain JPG or PNG label images.")
    return uploads


def _move_validated_upload(job_id: str, upload: ValidatedUpload) -> Path:
    """Move a staged upload into its final job upload directory.

    Parameters
    ----------
    job_id:
        Filesystem job identifier.
    upload:
        Validated upload metadata returned by ``_validate_image_upload``.

    Returns
    -------
    pathlib.Path
        Final randomized upload path under ``data/jobs/{job_id}/uploads``.
    """

    dest = job_dir(job_id) / "uploads" / upload.stored_filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    upload.temp_path.replace(dest)
    return dest


def _manifest_item_to_application(item: ManifestItem) -> ColaApplication:
    """Convert a parsed batch manifest item to a verification application.

    Parameters
    ----------
    item:
        Parsed CSV/JSON manifest item.

    Returns
    -------
    ColaApplication
        Application schema consumed by the rule registry.
    """

    payload = item.model_dump() if hasattr(item, "model_dump") else item.dict()
    payload.pop("panel_filenames", None)
    return ColaApplication(**payload)


def _manifest_item_filenames(item: ManifestItem) -> list[str]:
    """Return the image filenames referenced by one manifest application row."""

    return item.panel_filenames or [item.filename]


def _truthy(value: str | bool) -> bool:
    """Parse form-friendly boolean values."""

    if isinstance(value, bool):
        return value
    return value.lower() in {"1", "true", "yes", "on"}


def _combined_panel_ocr(filename: str, panel_ocrs: list[OCRResult]) -> OCRResult:
    """Aggregate OCR output across every submitted panel for one application."""

    if not panel_ocrs:
        return OCRResult(filename=filename, full_text="", avg_confidence=0.0, blocks=[], source="no panel OCR")
    blocks = []
    full_text_parts = []
    total_ms = 0
    ocr_ms = 0
    confidences = []
    sources = []
    for panel_index, ocr in enumerate(panel_ocrs, start=1):
        full_text_parts.append(f"[Panel {panel_index}: {ocr.filename}]\n{ocr.full_text}")
        total_ms += ocr.total_ms
        ocr_ms += ocr.ocr_ms
        confidences.append(ocr.avg_confidence)
        sources.append(ocr.source)
        for block in ocr.blocks:
            payload = block.model_dump() if hasattr(block, "model_dump") else dict(block)
            payload["panel_index"] = panel_index
            payload["panel_filename"] = ocr.filename
            blocks.append(payload)
    return OCRResult(
        filename=filename,
        full_text="\n\n".join(full_text_parts).strip(),
        avg_confidence=sum(confidences) / len(confidences),
        blocks=blocks,
        source=" + ".join(sorted(set(sources))),
        ocr_ms=ocr_ms,
        total_ms=total_ms,
    )


def _find_manifest_item(job_id: str, item_id: str) -> dict:
    """Return the manifest row for an item, if present."""

    manifest = load_manifest(job_id)
    for item in manifest.get("items", []):
        if item.get("item_id") == item_id:
            return item
    return {}


def _safe_upload_path(job_id: str, filename: str) -> Path:
    """Resolve a stored upload filename without allowing path traversal."""

    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    path = job_dir(job_id) / "uploads" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Upload image not found")
    return path


def _upload_filename_for_item(job_id: str, item_id: str, result_filename: str) -> str | None:
    """Find the stored upload filename for an item detail page."""

    item = _find_manifest_item(job_id, item_id)
    if isinstance(item.get("stored_filenames"), list) and item["stored_filenames"]:
        return item["stored_filenames"][0]
    return item.get("stored_filename") or item.get("filename") or result_filename


def _upload_filenames_for_item(job_id: str, item_id: str, result_filename: str) -> list[str]:
    """Return every stored upload filename for an item."""

    item = _find_manifest_item(job_id, item_id)
    if isinstance(item.get("stored_filenames"), list):
        return [Path(filename).name for filename in item["stored_filenames"]]
    filename = _upload_filename_for_item(job_id, item_id, result_filename)
    return [filename] if filename else []


def _queue_manifest_batch(
    *,
    manifest_items: list[ManifestItem],
    uploads: list[ValidatedUpload],
    job_label: str,
    review_unknown_government_warning: bool,
    require_review_before_rejection: bool,
    require_review_before_acceptance: bool,
) -> str:
    """Validate image/application matching, persist uploads, and enqueue a batch."""

    if len(manifest_items) > MAX_BATCH_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Batch contains more than the maximum {MAX_BATCH_ITEMS} applications.",
        )
    if not uploads:
        raise HTTPException(status_code=400, detail="Upload label images as JPG/PNG files, a directory, or a ZIP archive.")

    by_filename: dict[str, ValidatedUpload] = {}
    by_basename: dict[str, ValidatedUpload | None] = {}
    for upload in uploads:
        if upload.original_filename in by_filename:
            raise HTTPException(status_code=400, detail=f"Duplicate uploaded image: {upload.original_filename}")
        by_filename[upload.original_filename] = upload
        basename = PurePosixPath(upload.original_filename).name
        if basename in by_basename:
            by_basename[basename] = None
        else:
            by_basename[basename] = upload

    def upload_for_manifest_filename(filename: str) -> ValidatedUpload | None:
        """Return an uploaded image by exact relative key or unique basename."""

        return by_filename.get(filename) or by_basename.get(PurePosixPath(filename).name)

    expected_filenames = {filename for item in manifest_items for filename in _manifest_item_filenames(item)}
    used_uploads: set[str] = set()
    missing = []
    for filename in sorted(expected_filenames):
        upload = upload_for_manifest_filename(filename)
        if upload is None:
            missing.append(filename)
        else:
            used_uploads.add(upload.original_filename)
    extra = sorted(set(by_filename) - used_uploads)
    if missing:
        raise HTTPException(status_code=400, detail=f"Manifest references missing images: {', '.join(missing)}")
    if extra:
        raise HTTPException(status_code=400, detail=f"Uploaded images not referenced by manifest: {', '.join(extra)}")

    job_id = create_job(label=job_label)
    queued_items = []
    for item in manifest_items:
        item_uploads = [upload_for_manifest_filename(filename) for filename in _manifest_item_filenames(item)]
        if any(upload is None for upload in item_uploads):
            raise HTTPException(status_code=400, detail=f"Manifest references missing images for {item.filename}")
        item_uploads = [upload for upload in item_uploads if upload is not None]
        destinations = [_move_validated_upload(job_id, upload) for upload in item_uploads]
        item_id = item.fixture_id or Path(item.filename).stem
        add_manifest_item(
            job_id,
            {
                "item_id": item_id,
                "filename": item.filename,
                "fixture_id": item.fixture_id,
                "original_filename": item_uploads[0].original_filename,
                "stored_filename": item_uploads[0].stored_filename,
                "upload_size": sum(upload.upload_size for upload in item_uploads),
                "original_filenames": [upload.original_filename for upload in item_uploads],
                "stored_filenames": [upload.stored_filename for upload in item_uploads],
                "upload_sizes": [upload.upload_size for upload in item_uploads],
                "workflow": "batch_multi_panel_application" if len(item_uploads) > 1 else "batch_single_panel_application",
            },
        )
        item_payload = item.model_dump() if hasattr(item, "model_dump") else item.dict()
        queued_items.append(
            {
                "item": item_payload,
                "item_id": item_id,
                "stored_filename": item_uploads[0].stored_filename,
                "stored_filenames": [dest.name for dest in destinations],
                "original_filenames": [upload.original_filename for upload in item_uploads],
            }
        )

    enqueue_batch(
        job_id,
        {
            "items": queued_items,
            "review_unknown_government_warning": review_unknown_government_warning,
            "require_review_before_rejection": require_review_before_rejection,
            "require_review_before_acceptance": require_review_before_acceptance,
        },
    )
    return job_id


def _queue_manifest_batch_from_paths(
    *,
    manifest_items: list[ManifestItem],
    image_root: Path,
    job_label: str,
    review_unknown_government_warning: bool,
    require_review_before_rejection: bool,
    require_review_before_acceptance: bool,
) -> str:
    """Persist a server-side demo pack as a normal queued batch job.

    Parameters
    ----------
    manifest_items:
        Application rows selected from the server-side public COLA demo
        manifest.
    image_root:
        Root directory containing manifest-referenced image paths.
    job_label:
        Human-readable job label written to ``manifest.json``.

    Notes
    -----
    This intentionally copies the server-hosted demo images into ``data/jobs``
    so the resulting parse run is durable and inspectable like an uploaded job.
    """

    if len(manifest_items) > MAX_BATCH_ITEMS:
        raise HTTPException(status_code=400, detail=f"Batch contains more than the maximum {MAX_BATCH_ITEMS} applications.")
    job_id = create_job(label=job_label)
    queued_items = []
    for item in manifest_items:
        filenames = _manifest_item_filenames(item)
        source_paths = [_safe_demo_pack_path(image_root, filename) for filename in filenames]
        item_id = item.fixture_id or Path(item.filename).stem
        destinations = [
            save_upload(job_id, source_path, f"{item_id}_{index:02d}_{source_path.name}")
            for index, source_path in enumerate(source_paths, start=1)
        ]
        add_manifest_item(
            job_id,
            {
                "item_id": item_id,
                "filename": item.filename,
                "fixture_id": item.fixture_id,
                "original_filename": filenames[0],
                "stored_filename": destinations[0].name,
                "upload_size": sum(source_path.stat().st_size for source_path in source_paths),
                "original_filenames": filenames,
                "stored_filenames": [dest.name for dest in destinations],
                "upload_sizes": [source_path.stat().st_size for source_path in source_paths],
                "workflow": "server_public_cola_demo",
            },
        )
        item_payload = item.model_dump() if hasattr(item, "model_dump") else item.dict()
        queued_items.append(
            {
                "item": item_payload,
                "item_id": item_id,
                "stored_filename": destinations[0].name,
                "stored_filenames": [dest.name for dest in destinations],
                "original_filenames": filenames,
                "demo_ocr_filenames": [_demo_ocr_cache_name(item_id, filename) for filename in filenames],
                "demo_typography_filename": _demo_typography_cache_name(item_id),
            }
        )

    enqueue_batch(
        job_id,
        {
            "items": queued_items,
            "review_unknown_government_warning": review_unknown_government_warning,
            "require_review_before_rejection": require_review_before_rejection,
            "require_review_before_acceptance": require_review_before_acceptance,
        },
    )
    return job_id


def _demo_ocr_cache_name(item_id: str, image_filename: str) -> str:
    """Return the optional curated OCR cache path for one demo panel."""

    return f"ocr/{item_id}/{Path(image_filename).stem}.json"


def _demo_typography_cache_name(item_id: str) -> str:
    """Return the optional curated typography cache path for one demo app."""

    return f"typography/{item_id}.json"


def _safe_demo_cache_path(root: Path, relative_name: str) -> Path:
    """Resolve one server demo JSON cache path without allowing traversal."""

    normalized = relative_name.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.name or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=400, detail="Demo cache contains an unsafe path.")
    full_path = (root / path.as_posix()).resolve()
    if not full_path.is_relative_to(root.resolve()) or not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Demo cache missing: {relative_name}")
    if full_path.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail=f"Demo cache has unsupported suffix: {relative_name}")
    return full_path


def _load_public_cola_demo_ocr(relative_name: str) -> OCRResult | None:
    """Load a curated public-COLA demo OCR cache when one is present."""

    if not relative_name:
        return None
    try:
        payload = json.loads(_safe_demo_cache_path(PUBLIC_COLA_DEMO_DIR, relative_name).read_text(encoding="utf-8"))
        return OCRResult(**payload)
    except HTTPException:
        return None
    except (OSError, ValueError, TypeError):
        return None


def _load_public_cola_demo_typography(relative_name: str) -> dict[str, Any] | None:
    """Load a curated public-COLA demo typography cache when one is present."""

    if not relative_name:
        return None
    try:
        payload = json.loads(_safe_demo_cache_path(PUBLIC_COLA_DEMO_DIR, relative_name).read_text(encoding="utf-8"))
        return dict(payload)
    except HTTPException:
        return None
    except (OSError, ValueError, TypeError):
        return None


def _safe_demo_pack_path(root: Path, relative_name: str) -> Path:
    """Resolve one server demo image path without allowing traversal."""

    normalized = relative_name.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.name or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=400, detail="Demo manifest contains an unsafe image path.")
    full_path = (root / path.as_posix()).resolve()
    if not full_path.is_relative_to(root.resolve()) or not full_path.exists():
        raise HTTPException(status_code=400, detail=f"Demo image missing: {relative_name}")
    if full_path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Demo image has unsupported suffix: {relative_name}")
    if not has_allowed_image_signature(full_path) or not is_pillow_decodable_image(full_path):
        raise HTTPException(status_code=400, detail=f"Demo image is not a valid JPG/PNG: {relative_name}")
    return full_path


def _public_cola_demo_manifest_items() -> list[ManifestItem]:
    """Load the server-side public COLA demo manifest."""

    manifest_path = PUBLIC_COLA_DEMO_DIR / "manifest.csv"
    if not manifest_path.exists():
        return []
    return parse_manifest(manifest_path.name, manifest_path.read_bytes())


def _example_data_archive_path() -> Path:
    """Build and return a user-uploadable example-data ZIP.

    The original curated demo archive was created for internal server use and
    may contain image files without the root ``manifest.csv``. This archive is
    built specifically for users downloading the sample data from LOT Actual:
    it always includes one top-level folder containing ``manifest.csv``,
    ``README.md``, and the label-image tree.
    """

    manifest_path = PUBLIC_COLA_DEMO_DIR / "manifest.csv"
    images_root = PUBLIC_COLA_DEMO_DIR / "images"
    if not manifest_path.exists() or not images_root.exists():
        raise HTTPException(status_code=404, detail="Example data is not available on this server yet.")
    download_dir = JOBS_DIR / "_downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    archive_path = download_dir / "labels-on-tap-example-data.zip"
    newest_source_mtime = max(
        [manifest_path.stat().st_mtime]
        + [path.stat().st_mtime for path in images_root.rglob("*") if path.is_file()]
    )
    if archive_path.exists() and archive_path.stat().st_mtime >= newest_source_mtime:
        return archive_path
    with ZipFile(archive_path, "w") as archive:
        archive.write(manifest_path, "labels-on-tap-example-data/manifest.csv")
        readme_path = PUBLIC_COLA_DEMO_DIR / "README.md"
        if readme_path.exists():
            archive.write(readme_path, "labels-on-tap-example-data/README.md")
        else:
            archive.writestr(
                "labels-on-tap-example-data/README.md",
                "Upload this folder in LOT Actual. It contains manifest.csv and label images for testing.\n",
            )
        for path in sorted(images_root.rglob("*")):
            if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS:
                archive.write(path, Path("labels-on-tap-example-data/images") / path.relative_to(images_root))
    return archive_path


def _public_cola_demo_applications(items: list[ManifestItem]) -> list[dict[str, Any]]:
    """Return browser data for the server-side public COLA demo viewer."""

    applications = []
    for item in items:
        images = []
        for filename in _manifest_item_filenames(item):
            try:
                _safe_demo_pack_path(PUBLIC_COLA_DEMO_DIR, filename)
            except HTTPException:
                continue
            images.append({"url": f"/public-cola-demo/images/{filename}"})
        if images:
            applications.append(
                {
                    "id": item.filename,
                    "result_id": item.fixture_id or Path(item.filename).stem,
                    "images": images,
                    "actual_rows": _manifest_item_truth_rows(item),
                }
            )
    return applications


def _manifest_item_truth_rows(item: ManifestItem) -> list[dict[str, str]]:
    """Return application truth fields shown before parsing starts."""

    return [
        {"label": "Brand name", "actual": item.brand_name or "Not provided"},
        {"label": "Fanciful name", "actual": item.fanciful_name or "Not provided"},
        {"label": "Product type", "actual": item.product_type.replace("_", " ").title() if item.product_type else "Not provided"},
        {"label": "Class/type", "actual": item.class_type or "Not provided"},
        {"label": "Alcohol content", "actual": item.alcohol_content or "Not provided"},
        {"label": "Net contents", "actual": item.net_contents or "Not provided"},
        {"label": "Bottler / producer", "actual": item.bottler_producer_name_address or "Not provided"},
        {"label": "Imported", "actual": "Yes" if item.imported else "No"},
        {"label": "Country of origin", "actual": item.country_of_origin or "Not provided"},
        {"label": "Government warning text", "actual": CANONICAL_WARNING},
        {"label": "Government warning heading", "actual": "GOVERNMENT WARNING:"},
        {"label": "Government warning boldness", "actual": "Bold heading required"},
    ]


def _normalize_letters(text: str) -> str:
    """Uppercase text and keep only letters for heading detection."""

    return "".join(ch for ch in text.upper() if ch.isalpha())


def _bbox_bounds(bbox: object, *, image_width: int, image_height: int) -> tuple[float, float, float, float] | None:
    """Return normalized bbox bounds for two-point boxes or four-point polygons."""

    if not isinstance(bbox, list):
        return None
    points: list[tuple[float, float]] = []
    for point in bbox:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
    if not points:
        return None
    if max(max(abs(x), abs(y)) for x, y in points) > 1.5:
        points = [(x / max(image_width, 1), y / max(image_height, 1)) for x, y in points]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return max(0.0, min(xs)), max(0.0, min(ys)), min(1.0, max(xs)), min(1.0, max(ys))


def _warning_blocks(result: Any) -> list[dict[str, Any]]:
    """Return OCR blocks that appear to support the government warning heading."""

    blocks = result.ocr.get("blocks", []) if isinstance(result.ocr, dict) else []
    matches: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        text = str(block.get("text") or "")
        normalized = _normalize_letters(text)
        if "GOVERNMENTWARNING" in normalized or "GOVERNMENT" in normalized or "WARNING" in normalized:
            matches.append(
                {
                    "index": index,
                    "text": text,
                    "confidence": block.get("confidence"),
                    "bbox": block.get("bbox"),
                    "has_bbox": block.get("bbox") is not None,
                }
            )
    return matches


def _warning_crop_bounds(result: Any, image_path: Path) -> tuple[int, int, int, int] | None:
    """Compute a reviewer-visible crop around detected warning-heading OCR boxes."""

    blocks = _warning_blocks(result)
    if not blocks:
        return None
    with Image.open(image_path) as image:
        width, height = image.size
    bounds: list[tuple[float, float, float, float]] = []
    for block in blocks:
        bbox = _bbox_bounds(block.get("bbox"), image_width=width, image_height=height)
        if bbox is not None:
            bounds.append(bbox)
    if not bounds:
        return None
    x1 = min(bound[0] for bound in bounds)
    y1 = min(bound[1] for bound in bounds)
    x2 = max(bound[2] for bound in bounds)
    y2 = max(bound[3] for bound in bounds)
    crop_height = max((y2 - y1) * height, 1.0)
    pad_x = max(8, int(round(crop_height * 0.8)))
    pad_y = max(6, int(round(crop_height * 0.6)))
    return (
        max(0, int(round(x1 * width)) - pad_x),
        max(0, int(round(y1 * height)) - pad_y),
        min(width, int(round(x2 * width)) + pad_x),
        min(height, int(round(y2 * height)) + pad_y),
    )


def _assess_warning_typography(image_path: Path, ocr: Any) -> dict[str, Any]:
    """Run the deployable warning-heading boldness preflight.

    Notes
    -----
    Typography failures must never crash the review flow. A classifier or crop
    error becomes Needs Review, which is the conservative compliance outcome.
    """

    try:
        assessment, _ = assess_warning_heading_boldness(image_path, ocr)
        return assessment.to_dict()
    except Exception as exc:  # pragma: no cover - defensive web-route armor
        return {
            "verdict": "needs_review",
            "probability": None,
            "threshold": None,
            "crop_available": False,
            "model_name": "real-adapted-logistic-warning-heading-boldness",
            "model_version": "v1",
            "matched_text": "",
            "match_score": None,
            "ocr_confidence": None,
            "crop_ms": 0.0,
            "classification_ms": 0.0,
            "message": f"Typography preflight unavailable: {exc}",
            "reviewer_action": "Review the warning heading manually.",
        }


def _warning_evidence_context(job_id: str, item_id: str, result: Any) -> dict[str, Any]:
    """Build image, OCR, and crop metadata for the item detail evidence panel."""

    upload_filename = _upload_filename_for_item(job_id, item_id, result.filename)
    upload_filenames = _upload_filenames_for_item(job_id, item_id, result.filename)
    image_path = _safe_upload_path(job_id, upload_filename) if upload_filename else None
    blocks = _warning_blocks(result)
    try:
        crop_available = bool(image_path and detect_warning_heading_crop(image_path, result.ocr))
    except Exception:  # pragma: no cover - defensive evidence rendering
        crop_available = False
    return {
        "upload_filename": upload_filename,
        "image_url": f"/jobs/{job_id}/uploads/{upload_filename}" if upload_filename else None,
        "panel_image_urls": [
            {"filename": filename, "url": f"/jobs/{job_id}/uploads/{filename}"}
            for filename in upload_filenames
        ],
        "warning_crop_url": f"/jobs/{job_id}/items/{item_id}/warning-crop.png" if crop_available else None,
        "warning_blocks": blocks,
        "warning_text_detected": bool(blocks),
        "ocr_block_count": len(result.ocr.get("blocks", [])) if isinstance(result.ocr, dict) else 0,
    }


def _job_comparison_payload(results: list[Any]) -> dict[str, list[dict[str, Any]]]:
    """Build side-by-side application truth and parsed evidence rows for a job.

    Parameters
    ----------
    results:
        Completed verification results for one durable job.

    Returns
    -------
    dict[str, list[dict[str, Any]]]
        Mapping from item ID to comparison rows. Each row contains the
        application value, the parsed/OCR-supported value, verdict, and a short
        evidence snippet for display on the job page.
    """

    return {result.item_id: _result_comparison_rows(result) for result in results}


def _result_comparison_rows(result: Any) -> list[dict[str, Any]]:
    """Return reviewer-facing truth-vs-parsed rows for one application."""

    checks_by_rule = {check.rule_id: check for check in result.checks}
    application = result.application if isinstance(result.application, dict) else {}
    field_specs = [
        ("Brand name", "brand_name", "FORM_BRAND_MATCHES_LABEL"),
        ("Fanciful name", "fanciful_name", "FORM_FANCIFUL_NAME_MATCHES_LABEL"),
        ("Product type", "product_type", None),
        ("Class/type", "class_type", "FORM_CLASS_TYPE_MATCHES_LABEL"),
        ("Alcohol content", "alcohol_content", "FORM_ALCOHOL_CONTENT_MATCHES_LABEL"),
        ("Net contents", "net_contents", "FORM_NET_CONTENTS_MATCHES_LABEL"),
        ("Bottler / producer", "bottler_producer_name_address", "FORM_BOTTLER_NAME_ADDRESS_MATCHES_LABEL"),
        ("Imported", "imported", None),
        ("Country of origin", "country_of_origin", "COUNTRY_OF_ORIGIN_MATCH"),
        ("Government warning text", None, "GOV_WARNING_EXACT_TEXT"),
        ("Government warning heading", None, "GOV_WARNING_HEADER_CAPS"),
        ("Government warning boldness", None, "GOV_WARNING_HEADER_BOLD_REVIEW"),
    ]
    rows: list[dict[str, Any]] = []
    for label, app_key, rule_id in field_specs:
        check_obj = checks_by_rule.get(rule_id) if rule_id else None
        actual = _application_display_value(application, app_key) if app_key else (check_obj.expected if check_obj else "")
        parsed = check_obj.observed if check_obj else _unverified_parsed_value(label, actual)
        evidence = (check_obj.evidence_text or "") if check_obj else ""
        rows.append(
            {
                "label": label,
                "actual": actual or "Not provided",
                "parsed": parsed or "No parsed comparison",
                "verdict": check_obj.verdict if check_obj else "needs_review",
                "message": check_obj.message if check_obj else "Application context field; no direct OCR comparison rule.",
                "evidence": _compact_evidence(evidence),
            }
        )
    return rows


def _application_display_value(application: dict[str, Any], key: str | None) -> str:
    """Return a readable application-field value for the comparison table."""

    if not key:
        return ""
    value = application.get(key)
    if key == "imported":
        return "Yes" if bool(value) else "No"
    if key == "product_type" and value:
        return str(value).replace("_", " ").title()
    return str(value or "")


def _unverified_parsed_value(label: str, actual: str) -> str:
    """Render non-OCR context rows without implying a label match."""

    if label == "Product type":
        return "Used to select beverage-specific rules"
    if label == "Imported":
        return "Controls country-of-origin rule"
    return actual


def _compact_evidence(text: str, limit: int = 240) -> str:
    """Return a one-line evidence snippet for dense job-level tables."""

    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}..."


def _queue_timing_metrics(queue_status: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return progress and elapsed-time metrics for a queue status object."""

    if not queue_status:
        return None
    total = int(queue_status.get("total") or 0)
    processed = int(queue_status.get("processed") or 0)
    started_at = _parse_iso_datetime(queue_status.get("started_at"))
    finished_at = _parse_iso_datetime(queue_status.get("finished_at"))
    end_at = finished_at if finished_at else datetime.now(timezone.utc)
    elapsed_seconds = (end_at - started_at).total_seconds() if started_at else 0.0
    per_application = elapsed_seconds / processed if processed else 0.0
    progress_percent = round((processed / total) * 100, 1) if total else 0.0
    return {
        "progress_percent": progress_percent,
        "elapsed_label": _format_seconds(elapsed_seconds),
        "per_application_label": _format_seconds(per_application),
        "elapsed_seconds": elapsed_seconds,
        "per_application_seconds": per_application,
    }


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp from the local queue file."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _format_seconds(seconds: float) -> str:
    """Format short durations for the browser status panel."""

    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.1f}s"


@router.post("/jobs")
def create_single_job(
    brand_name: str = Form(...),
    product_type: str = Form("malt_beverage"),
    class_type: str = Form(""),
    fanciful_name: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    bottler_producer_name_address: str = Form(""),
    imported: str = Form("false"),
    country_of_origin: str = Form(""),
    review_unknown_government_warning: bool = Form(False),
    require_review_before_rejection: bool = Form(False),
    require_review_before_acceptance: bool = Form(False),
    label_image: UploadFile = File(...),
) -> RedirectResponse:
    """Create and process a single-label upload job.

    Parameters
    ----------
    brand_name, product_type, class_type, alcohol_content, net_contents:
        Application fields entered in the single-label form.
    imported, country_of_origin:
        Import-origin fields used by ``COUNTRY_OF_ORIGIN_MATCH``.
    label_image:
        JPG/PNG label image uploaded by the reviewer.

    Returns
    -------
    RedirectResponse
        Redirects to the job result page after processing.
    """

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="_upload-", dir=JOBS_DIR) as temp_dir:
        upload = _validate_image_upload(label_image, Path(temp_dir))
        job_id = create_job(label="single upload")
        dest = _move_validated_upload(job_id, upload)

    application = ColaApplication(
        filename=upload.original_filename,
        product_type=product_type,
        brand_name=brand_name,
        fanciful_name=fanciful_name,
        class_type=class_type,
        alcohol_content=alcohol_content,
        net_contents=net_contents,
        bottler_producer_name_address=bottler_producer_name_address,
        imported=_truthy(imported),
        country_of_origin=country_of_origin,
    )
    item_id = dest.stem
    fixture_id = Path(upload.original_filename).stem
    ocr = ocr_engine.run(dest, fixture_id=fixture_id)
    typography = _assess_warning_typography(dest, ocr)
    result = verify_label(
        job_id,
        item_id,
        application,
        ocr,
        typography=typography,
        review_unknown_government_warning=review_unknown_government_warning,
        require_review_before_rejection=require_review_before_rejection,
        require_review_before_acceptance=require_review_before_acceptance,
    )
    write_result(result)
    add_manifest_item(
        job_id,
        {
            "item_id": item_id,
            "filename": upload.original_filename,
            "original_filename": upload.original_filename,
            "stored_filename": upload.stored_filename,
            "upload_size": upload.upload_size,
        },
    )
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@router.post("/jobs/multipanel")
def create_multipanel_job(
    brand_name: str = Form(...),
    product_type: str = Form("malt_beverage"),
    class_type: str = Form(""),
    fanciful_name: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    bottler_producer_name_address: str = Form(""),
    imported: str = Form("false"),
    country_of_origin: str = Form(""),
    review_unknown_government_warning: bool = Form(False),
    require_review_before_rejection: bool = Form(False),
    require_review_before_acceptance: bool = Form(False),
    label_images: list[UploadFile] = File(...),
) -> RedirectResponse:
    """Verify one application against multiple submitted label panels."""

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="_upload-", dir=JOBS_DIR) as temp_dir:
        uploads = [_validate_image_upload(upload, Path(temp_dir)) for upload in label_images]
        job_id = create_job(label=f"multi-panel upload ({len(uploads)} panels)")
        destinations = [_move_validated_upload(job_id, upload) for upload in uploads]

    application = ColaApplication(
        filename="multi-panel application",
        product_type=product_type,
        brand_name=brand_name,
        fanciful_name=fanciful_name,
        class_type=class_type,
        alcohol_content=alcohol_content,
        net_contents=net_contents,
        bottler_producer_name_address=bottler_producer_name_address,
        imported=_truthy(imported),
        country_of_origin=country_of_origin,
    )
    item_id = "multi_panel_application"
    panel_ocrs = [
        ocr_engine.run(dest, fixture_id=Path(upload.original_filename).stem)
        for upload, dest in zip(uploads, destinations, strict=True)
    ]
    combined_ocr = _combined_panel_ocr(application.filename, panel_ocrs)
    typography = None
    for dest, panel_ocr in zip(destinations, panel_ocrs, strict=True):
        panel_typography = _assess_warning_typography(dest, panel_ocr)
        if panel_typography.get("verdict") == "pass":
            typography = panel_typography
            break
        typography = typography or panel_typography
    result = verify_label(
        job_id,
        item_id,
        application,
        combined_ocr,
        typography=typography,
        review_unknown_government_warning=review_unknown_government_warning,
        require_review_before_rejection=require_review_before_rejection,
        require_review_before_acceptance=require_review_before_acceptance,
    )
    write_result(result)
    add_manifest_item(
        job_id,
        {
            "item_id": item_id,
            "filename": application.filename,
            "original_filenames": [upload.original_filename for upload in uploads],
            "stored_filenames": [upload.stored_filename for upload in uploads],
            "upload_sizes": [upload.upload_size for upload in uploads],
            "workflow": "multi_panel_application",
        },
    )
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@router.post("/photo-intake")
def create_photo_intake_job(
    label_images: list[UploadFile] = File(...),
    selected_index: int = Form(0),
    parse_mode: str = Form("current"),
) -> RedirectResponse:
    """Run demonstration OCR extraction on one or more free-form photos.

    Parameters
    ----------
    label_images:
        JPG/PNG bottle, can, shelf, or flat label photos uploaded for OCR
        exploration.
    selected_index:
        Zero-based browser-selected image index used when ``parse_mode`` is
        ``current``.
    parse_mode:
        ``current`` parses only the displayed photo. ``all`` parses every
        uploaded photo sequentially.

    Returns
    -------
    RedirectResponse
        Redirects to a demonstration page showing extracted candidate fields.

    Notes
    -----
    This is not a COLA verification route. It shows what the OCR layer can
    extract when no application fields have been provided.
    """

    if not label_images:
        raise HTTPException(status_code=400, detail="Upload at least one label photo.")
    if parse_mode not in {"current", "all"}:
        raise HTTPException(status_code=400, detail="Invalid photo parse mode.")

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="_upload-", dir=JOBS_DIR) as temp_dir:
        staged_uploads = [_validate_image_upload(upload, Path(temp_dir)) for upload in label_images if upload.filename]
        if not staged_uploads:
            raise HTTPException(status_code=400, detail="Upload at least one label photo.")
        if parse_mode == "current":
            if selected_index < 0 or selected_index >= len(staged_uploads):
                raise HTTPException(status_code=400, detail="Selected photo index is out of range.")
            uploads = [staged_uploads[selected_index]]
        else:
            uploads = staged_uploads
        job_id = create_job(label="photo intake demo")
        moved = [(_move_validated_upload(job_id, upload), upload) for upload in uploads]

    item_ids: list[str] = []
    for dest, upload in moved:
        item_id = dest.stem
        fixture_id = Path(upload.original_filename).stem
        ocr = ocr_engine.run(dest, fixture_id=fixture_id)
        intake = parse_photo_intake(ocr)
        intake["job_id"] = job_id
        intake["item_id"] = item_id
        intake["original_filename"] = upload.original_filename
        intake["stored_filename"] = upload.stored_filename
        intake["upload_size"] = upload.upload_size
        write_json(job_dir(job_id) / "photo_intake" / f"{item_id}.json", intake)
        add_manifest_item(
            job_id,
            {
                "item_id": item_id,
                "filename": upload.original_filename,
                "original_filename": upload.original_filename,
                "stored_filename": upload.stored_filename,
                "upload_size": upload.upload_size,
                "workflow": "photo_intake_demo",
            },
        )
        item_ids.append(item_id)

    write_json(job_dir(job_id) / "photo_intake" / "index.json", {"item_ids": item_ids})
    return RedirectResponse(url=f"/photo-intake/{job_id}/{item_ids[0]}", status_code=303)


def _photo_intake_navigation(job_id: str, item_id: str) -> dict[str, Any]:
    """Return previous/next photo-intake navigation metadata."""

    index_path = job_dir(job_id) / "photo_intake" / "index.json"
    if index_path.exists():
        item_ids = [str(value) for value in read_json(index_path).get("item_ids", [])]
    else:
        item_ids = sorted(path.stem for path in (job_dir(job_id) / "photo_intake").glob("*.json") if path.name != "index.json")
    if item_id not in item_ids:
        item_ids = [item_id]
    index = item_ids.index(item_id)
    return {
        "item_ids": item_ids,
        "index": index,
        "count": len(item_ids),
        "previous_item_id": item_ids[index - 1] if len(item_ids) > 1 else None,
        "next_item_id": item_ids[(index + 1) % len(item_ids)] if len(item_ids) > 1 else None,
    }


@router.get("/photo-intake/{job_id}/{item_id}", response_class=HTMLResponse)
def photo_intake_detail(request: Request, job_id: str, item_id: str) -> HTMLResponse:
    """Render one photo-intake OCR extraction result."""

    path = job_dir(job_id) / "photo_intake" / f"{item_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Photo intake result not found")
    return templates.TemplateResponse(
        request,
        "photo_intake.html",
        {
            "job_id": job_id,
            "item_id": item_id,
            "manifest": load_manifest(job_id),
            "intake": read_json(path),
            "navigation": _photo_intake_navigation(job_id, item_id),
        },
    )


@router.get("/photo-intake/{job_id}/{item_id}/image")
def photo_intake_image(job_id: str, item_id: str) -> FileResponse:
    """Serve the uploaded photo for the photo-intake result page."""

    intake_path = job_dir(job_id) / "photo_intake" / f"{item_id}.json"
    if not intake_path.exists():
        raise HTTPException(status_code=404, detail="Photo intake result not found")
    intake = read_json(intake_path)
    image_path = job_dir(job_id) / "uploads" / intake["stored_filename"]
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Photo image not found")
    return FileResponse(image_path)


@router.get("/cola-cloud-demo")
def create_cola_cloud_demo(request: Request, ttb_id: str | None = None) -> Response:
    """Create a side-by-side demo from local COLA Cloud-derived public data.

    Parameters
    ----------
    ttb_id:
        Optional TTB ID to display. When omitted, a deterministic demo record is
        selected from the local gitignored corpus.

    Returns
    -------
    HTMLResponse | RedirectResponse
        Friendly missing-data page when the local corpus is absent, otherwise a
        redirect to the generated comparison page.

    Notes
    -----
    This route reads already-downloaded files from ``data/work/cola``. It does
    not call COLA Cloud or TTB at runtime.
    """

    source = load_cola_cloud_demo_source(ttb_id)
    if source is None:
        return templates.TemplateResponse(
            request,
            "cola_cloud_demo_missing.html",
            {"requested_ttb_id": ttb_id},
            status_code=404,
        )

    job_id = create_job(label=f"COLA Cloud public example {source.ttb_id}")
    panel_ocrs = []
    for panel in source.panels:
        dest = save_upload(job_id, panel.image_path, panel.image_path.name)
        copied_panel = replace(panel, image_path=dest, stored_filename=dest.name)
        ocr = load_cached_conveyor_ocr(panel.image_path) or ocr_engine.run(panel.image_path, fixture_id=source.ttb_id)
        panel_ocrs.append((copied_panel, ocr))
        add_manifest_item(
            job_id,
            {
                "item_id": dest.stem,
                "filename": panel.filename,
                "stored_filename": dest.name,
                "panel_order": panel.panel_order,
                "image_type": panel.image_type,
                "workflow": "cola_cloud_public_example",
            },
        )

    payload = build_comparison_payload(source=source, panel_ocrs=panel_ocrs)
    payload["job_id"] = job_id
    write_json(job_dir(job_id) / "cola_cloud_demo" / "result.json", payload)
    return RedirectResponse(url=f"/cola-cloud-demo/{job_id}", status_code=303)


@router.get("/cola-cloud-demo/{job_id}", response_class=HTMLResponse)
def cola_cloud_demo_detail(request: Request, job_id: str) -> HTMLResponse:
    """Render the side-by-side COLA Cloud public example comparison."""

    path = job_dir(job_id) / "cola_cloud_demo" / "result.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="COLA Cloud demo result not found")
    return templates.TemplateResponse(
        request,
        "cola_cloud_demo.html",
        {
            "job_id": job_id,
            "demo": read_json(path),
        },
    )


@router.get("/cola-cloud-demo/{job_id}/images/{filename}")
def cola_cloud_demo_image(job_id: str, filename: str) -> FileResponse:
    """Serve a copied local demo label panel image for one generated job."""

    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid image filename")
    image_path = job_dir(job_id) / "uploads" / safe_name
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)


@router.get("/review", response_class=HTMLResponse)
def review_dashboard(request: Request, queue: str = "all") -> HTMLResponse:
    """Render a lightweight reviewer dashboard across all filesystem jobs."""

    rows: list[dict[str, Any]] = []
    queue_counts = {
        "ready_to_accept": 0,
        "acceptance_review": 0,
        "manual_evidence_review": 0,
        "rejection_review": 0,
        "ready_to_reject": 0,
    }
    job_count = 0
    if JOBS_DIR.exists():
        for path in sorted(JOBS_DIR.iterdir(), key=lambda candidate: candidate.stat().st_mtime, reverse=True):
            if not path.is_dir() or not (path / "manifest.json").exists():
                continue
            job_id = path.name
            try:
                manifest = load_manifest(job_id)
                results = list_results(job_id)
            except Exception:
                continue
            job_count += 1
            queue_status = load_queue_status(job_id)
            for result in results:
                queue_counts[result.policy_queue] = queue_counts.get(result.policy_queue, 0) + 1
                if queue != "all" and result.policy_queue != queue:
                    continue
                rows.append(
                    {
                        "job_id": job_id,
                        "job_label": manifest.get("label", ""),
                        "item_id": result.item_id,
                        "filename": result.filename,
                        "overall_verdict": result.overall_verdict,
                        "policy_queue": result.policy_queue,
                        "top_reason": result.top_reason,
                        "reviewer_decision": result.reviewer_decision,
                        "reviewed_at": result.reviewed_at,
                        "queue_status": queue_status.get("status") if queue_status else "",
                    }
                )
    return templates.TemplateResponse(
        request,
        "review_dashboard.html",
        {
            "rows": rows,
            "selected_queue": queue,
            "queue_counts": queue_counts,
            "job_count": job_count,
            "total_items": sum(queue_counts.values()),
        },
    )


@router.get("/public-cola-demo", response_class=HTMLResponse)
def public_cola_demo(request: Request, job_id: str = "") -> HTMLResponse:
    """Render the server-side public COLA demo browser and parse results."""

    items = _public_cola_demo_manifest_items()
    results = []
    manifest: dict[str, Any] = {"items": [], "label": "No demo parse run yet"}
    queue_status = None
    if job_id:
        try:
            manifest = load_manifest(job_id)
            results = list_results(job_id)
            queue_status = load_queue_status(job_id)
        except Exception:
            job_id = ""
    return templates.TemplateResponse(
        request,
        "public_cola_demo.html",
        {
            "applications": _public_cola_demo_applications(items),
            "missing_pack": not items,
            "demo_dir": PUBLIC_COLA_DEMO_DIR,
            "job_id": job_id,
            "manifest": manifest,
            "results": results,
            "queue_status": queue_status,
            "queue_timing": _queue_timing_metrics(queue_status),
            "comparison_rows": _job_comparison_payload(results),
        },
    )


@router.post("/public-cola-demo/parse")
def parse_public_cola_demo(
    parse_scope: str = Form("application"),
    selected_application: str = Form(""),
    review_policy: str = Form("human"),
    review_unknown_government_warning: bool = Form(False),
    require_review_before_rejection: bool = Form(False),
    require_review_before_acceptance: bool = Form(False),
) -> RedirectResponse:
    """Queue parsing for one server-hosted application or the full demo pack."""

    manifest_items = _public_cola_demo_manifest_items()
    if not manifest_items:
        raise HTTPException(status_code=404, detail=f"Public COLA demo pack missing at {PUBLIC_COLA_DEMO_DIR}")
    if parse_scope not in {"application", "directory"}:
        raise HTTPException(status_code=400, detail="Invalid parse scope.")
    if review_policy not in {"human", "auto"}:
        raise HTTPException(status_code=400, detail="Invalid review policy.")
    if review_policy == "human":
        review_unknown_government_warning = True
        require_review_before_rejection = True
        require_review_before_acceptance = True
    elif review_policy == "auto":
        review_unknown_government_warning = False
        require_review_before_rejection = False
        require_review_before_acceptance = False
    selected_application = selected_application.strip()
    if parse_scope == "application":
        if not selected_application:
            raise HTTPException(status_code=400, detail="Choose an application before parsing a single application.")
        manifest_items = [item for item in manifest_items if item.filename == selected_application or item.fixture_id == selected_application]
        if not manifest_items:
            raise HTTPException(status_code=400, detail=f"Selected application was not found: {selected_application}")
    job_id = _queue_manifest_batch_from_paths(
        manifest_items=manifest_items,
        image_root=PUBLIC_COLA_DEMO_DIR,
        job_label=(
            f"public COLA demo application {selected_application}"
            if parse_scope == "application"
            else f"public COLA demo directory ({len(manifest_items)} applications)"
        ),
        review_unknown_government_warning=review_unknown_government_warning,
        require_review_before_rejection=require_review_before_rejection,
        require_review_before_acceptance=require_review_before_acceptance,
    )
    return RedirectResponse(url=f"/public-cola-demo?job_id={job_id}", status_code=303)


@router.post("/public-cola-demo/reset")
def reset_public_cola_demo(job_id: str = Form("")) -> RedirectResponse:
    """Clear one server-side demo parse run and return to the demo browser."""

    if job_id:
        delete_job(job_id)
    return RedirectResponse(url="/public-cola-demo", status_code=303)


@router.get("/public-cola-demo/comparison-data/{job_id}")
def public_cola_demo_comparison_data(job_id: str) -> dict[str, Any]:
    """Return current demo parse rows for the application browser table."""

    queue_status = load_queue_status(job_id)
    results = list_results(job_id)
    return {
        "queue_status": queue_status,
        "comparison_rows": _job_comparison_payload(results),
    }


@router.get("/public-cola-demo/images/{image_path:path}")
def public_cola_demo_image(image_path: str) -> FileResponse:
    """Serve one image from the server-side public COLA demo pack."""

    return FileResponse(_safe_demo_pack_path(PUBLIC_COLA_DEMO_DIR, image_path))


@router.get("/example-data")
def download_example_data() -> FileResponse:
    """Download the server-hosted example application folder as a ZIP file."""

    archive_path = _example_data_archive_path()
    if not archive_path.exists() or not archive_path.is_file():
        raise HTTPException(status_code=404, detail="Example data is not available on this server yet.")
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="labels-on-tap-example-data.zip",
    )


@router.post("/jobs/batch")
def create_batch_job(
    background_tasks: BackgroundTasks,
    manifest_file: UploadFile = File(...),
    label_images: list[UploadFile] | None = File(None),
    image_archive: UploadFile | None = File(None),
    review_unknown_government_warning: bool = Form(False),
    require_review_before_rejection: bool = Form(False),
    require_review_before_acceptance: bool = Form(False),
) -> RedirectResponse:
    """Create and process a manifest-backed batch upload job.

    Parameters
    ----------
    manifest_file:
        CSV or JSON manifest with one row/item per label image.
    label_images, image_archive:
        Uploaded label images referenced by the manifest. Reviewers can upload
        loose image files, one ZIP archive, or both.

    Returns
    -------
    RedirectResponse
        Redirects to the batch job result page after scheduling background
        processing.

    Raises
    ------
    HTTPException
        Raised when the manifest is malformed, referenced images are missing,
        extra images are supplied, or any image fails upload preflight.

    Notes
    -----
    The route writes a durable queue record and returns immediately. A local
    filesystem-backed worker processes pending jobs and recovers interrupted
    running jobs on application startup.
    """

    del background_tasks
    if not manifest_file.filename:
        raise HTTPException(status_code=400, detail="Missing manifest filename")
    try:
        manifest_content = read_upload_with_size_limit(manifest_file.file, MAX_MANIFEST_BYTES)
        manifest_items = parse_manifest(manifest_file.filename, manifest_content)
    except (ValueError, ManifestParseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="_upload-", dir=JOBS_DIR) as temp_dir:
        uploads = [
            _validate_image_upload_with_policy(upload, Path(temp_dir), allow_relative_name=True)
            for upload in (label_images or [])
            if upload.filename
        ]
        if image_archive is not None and image_archive.filename:
            uploads.extend(_validate_zip_upload(image_archive, Path(temp_dir)))
        job_id = _queue_manifest_batch(
            manifest_items=manifest_items,
            uploads=uploads,
            job_label=f"batch upload ({len(manifest_items)} applications)",
            review_unknown_government_warning=review_unknown_government_warning,
            require_review_before_rejection=require_review_before_rejection,
            require_review_before_acceptance=require_review_before_acceptance,
        )
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@router.post("/jobs/application-directory")
def create_application_directory_job(
    application_directory: list[UploadFile] = File(...),
    parse_scope: str = Form("directory"),
    selected_application: str = Form(""),
    review_policy: str = Form("human"),
    review_unknown_government_warning: bool = Form(False),
    require_review_before_rejection: bool = Form(False),
    require_review_before_acceptance: bool = Form(False),
) -> RedirectResponse:
    """Create a durable demo job from one uploaded application directory.

    The selected directory must contain ``manifest.csv`` or ``manifest.json``
    plus the image paths referenced by the manifest. Browser directory uploads
    include the selected root folder name, so this route strips that common root
    before matching manifest panel paths such as ``images/TTB/front.png``.
    """

    files = [upload for upload in application_directory if upload.filename]
    if not files:
        raise HTTPException(status_code=400, detail="Select a directory containing manifest.csv and label images.")

    manifest_uploads = []
    for upload in files:
        try:
            key = _safe_directory_key(upload.filename or "")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if PurePosixPath(key).name.lower() in {"manifest.csv", "manifest.json"}:
            manifest_uploads.append((key, upload))
    if len(manifest_uploads) != 1:
        raise HTTPException(status_code=400, detail="Directory upload must contain exactly one manifest.csv or manifest.json file.")

    manifest_key, manifest_upload = manifest_uploads[0]
    root_prefix = PurePosixPath(manifest_key).parent.as_posix()
    if root_prefix == ".":
        root_prefix = ""
    try:
        manifest_content = read_upload_with_size_limit(manifest_upload.file, MAX_MANIFEST_BYTES)
        manifest_items = parse_manifest(PurePosixPath(manifest_key).name, manifest_content)
    except (ValueError, ManifestParseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if parse_scope not in {"application", "directory"}:
        raise HTTPException(status_code=400, detail="Invalid parse scope.")
    if review_policy not in {"human", "auto"}:
        raise HTTPException(status_code=400, detail="Invalid review policy.")
    if review_policy == "human":
        review_unknown_government_warning = True
        require_review_before_rejection = True
        require_review_before_acceptance = True
    elif review_policy == "auto":
        review_unknown_government_warning = False
        require_review_before_rejection = False
        require_review_before_acceptance = False
    selected_application = selected_application.strip()
    if parse_scope == "application":
        if not selected_application:
            raise HTTPException(status_code=400, detail="Choose an application before parsing a single application.")
        manifest_items = [
            item
            for item in manifest_items
            if item.filename == selected_application or item.fixture_id == selected_application
        ]
        if not manifest_items:
            raise HTTPException(status_code=400, detail=f"Selected application was not found in the manifest: {selected_application}")
    expected_upload_names = {filename for item in manifest_items for filename in _manifest_item_filenames(item)}

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="_upload-", dir=JOBS_DIR) as temp_dir:
        uploads: list[ValidatedUpload] = []
        for upload in files:
            key = _safe_directory_key(upload.filename or "")
            if key == manifest_key:
                continue
            if PurePosixPath(key).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
                continue
            relative_key = _strip_directory_root(key, root_prefix)
            if relative_key not in expected_upload_names:
                continue
            staged = _validate_image_upload_with_policy(upload, Path(temp_dir), allow_relative_name=True)
            staged.original_filename = _strip_directory_root(staged.original_filename, root_prefix)
            uploads.append(staged)
        job_id = _queue_manifest_batch(
            manifest_items=manifest_items,
            uploads=uploads,
            job_label=(
                f"single application demo upload ({selected_application})"
                if parse_scope == "application"
                else f"directory demo upload ({len(manifest_items)} applications)"
            ),
            review_unknown_government_warning=review_unknown_government_warning,
            require_review_before_rejection=require_review_before_rejection,
            require_review_before_acceptance=require_review_before_acceptance,
        )
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


def _process_batch_items(
    job_id: str,
    queued_items: list[dict[str, Any]],
    review_unknown_government_warning: bool,
    require_review_before_rejection: bool,
    require_review_before_acceptance: bool,
    progress_callback: Any | None = None,
) -> None:
    """Process queued batch items and write one result file per item."""

    total = len(queued_items)
    for index, queued in enumerate(queued_items, start=1):
        item = ManifestItem(**queued["item"])
        item_id = queued["item_id"]
        if (job_dir(job_id) / "results" / f"{item_id}.json").exists():
            if progress_callback:
                progress_callback(index, total)
            continue
        application = _manifest_item_to_application(item)
        stored_filenames = queued.get("stored_filenames") or [queued["stored_filename"]]
        destinations = [job_dir(job_id) / "uploads" / Path(filename).name for filename in stored_filenames]
        fixture_ids = [
            Path(filename).stem
            for filename in (queued.get("original_filenames") or _manifest_item_filenames(item))
        ]
        demo_ocr_filenames = queued.get("demo_ocr_filenames") or []
        panel_ocrs = []
        for panel_index, (dest, fixture_id) in enumerate(zip(destinations, fixture_ids, strict=True)):
            demo_ocr = (
                _load_public_cola_demo_ocr(str(demo_ocr_filenames[panel_index]))
                if panel_index < len(demo_ocr_filenames)
                else None
            )
            panel_ocrs.append(demo_ocr or ocr_engine.run(dest, fixture_id=fixture_id))
        ocr = _combined_panel_ocr(application.filename, panel_ocrs) if len(panel_ocrs) > 1 else panel_ocrs[0]
        typography = _load_public_cola_demo_typography(str(queued.get("demo_typography_filename") or ""))
        if typography is None:
            for dest, panel_ocr in zip(destinations, panel_ocrs, strict=True):
                panel_typography = _assess_warning_typography(dest, panel_ocr)
                if panel_typography.get("verdict") == "pass":
                    typography = panel_typography
                    break
                typography = typography or panel_typography
        result = verify_label(
            job_id,
            item_id,
            application,
            ocr,
            typography=typography,
            review_unknown_government_warning=review_unknown_government_warning,
            require_review_before_rejection=require_review_before_rejection,
            require_review_before_acceptance=require_review_before_acceptance,
        )
        write_result(result)
        if progress_callback:
            progress_callback(index, total)


def process_queued_batch_job(job_id: str, payload: dict[str, Any], progress_callback: Any | None = None) -> None:
    """Queue-worker entry point used by the app startup worker."""

    _process_batch_items(
        job_id,
        payload.get("items", []),
        bool(payload.get("review_unknown_government_warning")),
        bool(payload.get("require_review_before_rejection")),
        bool(payload.get("require_review_before_acceptance")),
        progress_callback=progress_callback,
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(request: Request, job_id: str):
    """Render a job's result table."""

    results = list_results(job_id)
    queue_status = load_queue_status(job_id)
    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "job_id": job_id,
            "manifest": load_manifest(job_id),
            "results": results,
            "queue_status": queue_status,
            "queue_timing": _queue_timing_metrics(queue_status),
            "comparison_rows": _job_comparison_payload(results),
        },
    )


@router.get("/jobs/{job_id}/status", response_class=HTMLResponse)
def job_status(request: Request, job_id: str):
    """Render the HTMX status/result table partial for a job."""

    results = list_results(job_id)
    queue_status = load_queue_status(job_id)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {
            "job_id": job_id,
            "results": results,
            "manifest": load_manifest(job_id),
            "queue_status": queue_status,
            "queue_timing": _queue_timing_metrics(queue_status),
            "comparison_rows": _job_comparison_payload(results),
        },
    )


@router.get("/jobs/{job_id}/items/{item_id}", response_class=HTMLResponse)
def item_detail(request: Request, job_id: str, item_id: str):
    """Render per-item evidence, OCR text, and rule checks."""

    result = load_result(job_id, item_id)
    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {"job_id": job_id, "result": result, "evidence": _warning_evidence_context(job_id, item_id, result)},
    )


@router.post("/jobs/{job_id}/items/{item_id}/review")
def save_reviewer_decision(
    job_id: str,
    item_id: str,
    reviewer_decision: str = Form(...),
    reviewer_note: str = Form(""),
    return_to: str = Form("item"),
) -> RedirectResponse:
    """Persist a lightweight reviewer decision and note for one result."""

    allowed = {"accept", "reject", "request_correction", "override", "escalate"}
    if reviewer_decision not in allowed:
        raise HTTPException(status_code=400, detail="Invalid reviewer decision")
    if reviewer_decision in {"override", "escalate"} and not reviewer_note.strip():
        raise HTTPException(status_code=400, detail="Override and escalation decisions require a note.")
    result = load_result(job_id, item_id)
    result.reviewer_decision = reviewer_decision
    result.reviewer_note = reviewer_note.strip()
    result.reviewed_at = datetime.now(timezone.utc).isoformat()
    write_result(result)
    if return_to == "job":
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
    return RedirectResponse(url=f"/jobs/{job_id}/items/{item_id}", status_code=303)


@router.get("/jobs/{job_id}/uploads/{filename}")
def job_upload_image(job_id: str, filename: str) -> FileResponse:
    """Serve the stored label image for a job item evidence page."""

    return FileResponse(_safe_upload_path(job_id, filename))


@router.get("/jobs/{job_id}/items/{item_id}/warning-crop.png")
def warning_heading_crop(job_id: str, item_id: str) -> Response:
    """Serve a crop around OCR-detected government-warning heading evidence."""

    result = load_result(job_id, item_id)
    upload_filename = _upload_filename_for_item(job_id, item_id, result.filename)
    if not upload_filename:
        raise HTTPException(status_code=404, detail="Upload image not found")
    image_path = _safe_upload_path(job_id, upload_filename)
    try:
        evidence = detect_warning_heading_crop(image_path, result.ocr)
    except Exception as exc:  # pragma: no cover - defensive evidence rendering
        raise HTTPException(status_code=404, detail="Warning heading crop not available") from exc
    if evidence is None:
        raise HTTPException(status_code=404, detail="Warning heading crop not available")
    crop = evidence.crop.convert("RGB")
    buffer = BytesIO()
    crop.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")


@router.get("/jobs/{job_id}/results.csv")
def csv_export(job_id: str) -> Response:
    """Export all job results as CSV."""

    csv_text = results_to_csv(list_results(job_id))
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="labels-on-tap-{job_id}.csv"'},
    )
