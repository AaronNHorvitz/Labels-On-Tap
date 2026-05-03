"""Job creation, upload processing, result pages, and CSV export routes.

Notes
-----
The sprint prototype uses synchronous processing and a filesystem job store.
That keeps the implementation inspectable for the take-home while preserving a
clear future path to background workers if batch sizes grow.
"""

from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image

from app.config import JOBS_DIR, MAX_MANIFEST_BYTES, MAX_UPLOAD_BYTES, ROOT
from app.schemas.application import ColaApplication
from app.schemas.manifest import ManifestItem
from app.services.csv_export import results_to_csv
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
    copy_upload_with_size_limit,
    random_upload_filename,
    read_upload_with_size_limit,
    validate_upload_name,
)
from app.services.rules.registry import verify_label


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
    return item.get("stored_filename") or item.get("filename") or result_filename


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


def _warning_evidence_context(job_id: str, item_id: str, result: Any) -> dict[str, Any]:
    """Build image, OCR, and crop metadata for the item detail evidence panel."""

    upload_filename = _upload_filename_for_item(job_id, item_id, result.filename)
    image_path = _safe_upload_path(job_id, upload_filename) if upload_filename else None
    blocks = _warning_blocks(result)
    crop_available = bool(image_path and _warning_crop_bounds(result, image_path))
    return {
        "upload_filename": upload_filename,
        "image_url": f"/jobs/{job_id}/uploads/{upload_filename}" if upload_filename else None,
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
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    imported: str = Form("false"),
    country_of_origin: str = Form(""),
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
        Redirects to the job result page after synchronous processing.
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
        class_type=class_type,
        alcohol_content=alcohol_content,
        net_contents=net_contents,
        imported=imported.lower() in {"1", "true", "yes", "on"},
        country_of_origin=country_of_origin,
    )
    item_id = dest.stem
    fixture_id = Path(upload.original_filename).stem
    ocr = ocr_engine.run(dest, fixture_id=fixture_id)
    result = verify_label(job_id, item_id, application, ocr)
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


@router.post("/jobs/batch")
def create_batch_job(
    manifest_file: UploadFile = File(...),
    label_images: list[UploadFile] = File(...),
) -> RedirectResponse:
    """Create and process a manifest-backed batch upload job.

    Parameters
    ----------
    manifest_file:
        CSV or JSON manifest with one row/item per label image.
    label_images:
        Uploaded label images referenced by the manifest.

    Returns
    -------
    RedirectResponse
        Redirects to the batch job result page after synchronous processing.

    Raises
    ------
    HTTPException
        Raised when the manifest is malformed, referenced images are missing,
        extra images are supplied, or any image fails upload preflight.

    Notes
    -----
    Batch work is synchronous for the take-home. A production implementation
    should enqueue OCR/rule work and stream progress from a worker-backed store.
    """

    if not manifest_file.filename:
        raise HTTPException(status_code=400, detail="Missing manifest filename")
    try:
        manifest_content = read_upload_with_size_limit(manifest_file.file, MAX_MANIFEST_BYTES)
        manifest_items = parse_manifest(manifest_file.filename, manifest_content)
    except (ValueError, ManifestParseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="_upload-", dir=JOBS_DIR) as temp_dir:
        uploads = [_validate_image_upload(upload, Path(temp_dir)) for upload in label_images]
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
        for item in manifest_items:
            upload = by_filename[item.filename]
            dest = _move_validated_upload(job_id, upload)
            item_id = item.fixture_id or dest.stem
            application = _manifest_item_to_application(item)
            fixture_id = item.fixture_id or Path(item.filename).stem
            ocr = ocr_engine.run(dest, fixture_id=fixture_id)
            result = verify_label(job_id, item_id, application, ocr)
            write_result(result)
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

    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


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
        },
    )


@router.get("/jobs/{job_id}/status", response_class=HTMLResponse)
def job_status(request: Request, job_id: str):
    """Render the HTMX status/result table partial for a job."""

    results = list_results(job_id)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"job_id": job_id, "results": results, "manifest": load_manifest(job_id)},
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
    crop_bounds = _warning_crop_bounds(result, image_path)
    if crop_bounds is None:
        raise HTTPException(status_code=404, detail="Warning heading crop not available")
    with Image.open(image_path) as image:
        crop = image.convert("RGB").crop(crop_bounds)
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
