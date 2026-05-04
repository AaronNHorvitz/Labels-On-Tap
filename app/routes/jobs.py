"""Job creation, upload processing, result pages, and CSV export routes.

Notes
-----
The sprint prototype uses a filesystem job store. Single uploads process
immediately; manifest-backed batch uploads write a durable local queue record
so the browser can redirect to a polling progress page while a local worker
writes results.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image

from app.config import JOBS_DIR, MAX_ARCHIVE_BYTES, MAX_BATCH_ITEMS, MAX_MANIFEST_BYTES, MAX_UPLOAD_BYTES, ROOT
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

    if not upload.filename:
        raise HTTPException(status_code=400, detail="Missing upload filename")
    original_filename = upload.filename
    try:
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


def _validate_image_bytes(original_filename: str, content: bytes, temp_dir: Path) -> ValidatedUpload:
    """Validate one in-memory image extracted from a ZIP archive."""

    try:
        validate_upload_name(original_filename)
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
            original_filename = Path(member.filename).name
            if not original_filename:
                continue
            if Path(original_filename).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
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
    return ColaApplication(**payload)


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
    label_image: UploadFile = File(...),
) -> RedirectResponse:
    """Run demonstration OCR extraction on a free-form label photo.

    Parameters
    ----------
    label_image:
        JPG/PNG bottle, can, or label photo uploaded for OCR exploration.

    Returns
    -------
    RedirectResponse
        Redirects to a demonstration page showing extracted candidate fields.

    Notes
    -----
    This is not a COLA verification route. It shows what the OCR layer can
    extract when no application fields have been provided.
    """

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="_upload-", dir=JOBS_DIR) as temp_dir:
        upload = _validate_image_upload(label_image, Path(temp_dir))
        job_id = create_job(label="photo intake demo")
        dest = _move_validated_upload(job_id, upload)

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
    return RedirectResponse(url=f"/photo-intake/{job_id}/{item_id}", status_code=303)


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
        },
    )


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
        uploads = [_validate_image_upload(upload, Path(temp_dir)) for upload in (label_images or []) if upload.filename]
        if image_archive is not None and image_archive.filename:
            uploads.extend(_validate_zip_upload(image_archive, Path(temp_dir)))
        if not uploads:
            raise HTTPException(status_code=400, detail="Upload label images as loose JPG/PNG files or a ZIP archive.")
        if len(uploads) > MAX_BATCH_ITEMS:
            raise HTTPException(status_code=400, detail=f"Batch contains more than the maximum {MAX_BATCH_ITEMS} label images.")
        by_filename: dict[str, ValidatedUpload] = {}
        for upload in uploads:
            if upload.original_filename in by_filename:
                raise HTTPException(status_code=400, detail=f"Duplicate uploaded image: {upload.original_filename}")
            by_filename[upload.original_filename] = upload

        expected_filenames = {item.filename for item in manifest_items}
        uploaded_filenames = set(by_filename)
        missing = sorted(expected_filenames - uploaded_filenames)
        extra = sorted(uploaded_filenames - expected_filenames)
        if missing:
            raise HTTPException(status_code=400, detail=f"Manifest references missing images: {', '.join(missing)}")
        if extra:
            raise HTTPException(status_code=400, detail=f"Uploaded images not referenced by manifest: {', '.join(extra)}")

        job_id = create_job(label=f"batch upload ({len(manifest_items)} labels)")
        queued_items = []
        for item in manifest_items:
            upload = by_filename[item.filename]
            dest = _move_validated_upload(job_id, upload)
            item_id = item.fixture_id or dest.stem
            add_manifest_item(
                job_id,
                {
                    "item_id": item_id,
                    "filename": item.filename,
                    "fixture_id": item.fixture_id,
                    "original_filename": upload.original_filename,
                    "stored_filename": upload.stored_filename,
                    "upload_size": upload.upload_size,
                },
            )
            item_payload = item.model_dump() if hasattr(item, "model_dump") else item.dict()
            queued_items.append(
                {
                    "item": item_payload,
                    "item_id": item_id,
                    "stored_filename": upload.stored_filename,
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
        dest = job_dir(job_id) / "uploads" / queued["stored_filename"]
        application = _manifest_item_to_application(item)
        fixture_id = item.fixture_id or Path(item.filename).stem
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

    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "job_id": job_id,
            "manifest": load_manifest(job_id),
            "results": list_results(job_id),
            "queue_status": load_queue_status(job_id),
        },
    )


@router.get("/jobs/{job_id}/status", response_class=HTMLResponse)
def job_status(request: Request, job_id: str):
    """Render the HTMX status/result table partial for a job."""

    results = list_results(job_id)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"job_id": job_id, "results": results, "manifest": load_manifest(job_id), "queue_status": load_queue_status(job_id)},
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
