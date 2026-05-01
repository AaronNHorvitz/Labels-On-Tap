from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import JOBS_DIR, MAX_MANIFEST_BYTES, MAX_UPLOAD_BYTES, ROOT
from app.schemas.application import ColaApplication
from app.schemas.manifest import ManifestItem
from app.services.csv_export import results_to_csv
from app.services.job_store import (
    add_manifest_item,
    create_job,
    job_dir,
    list_results,
    load_manifest,
    load_result,
    write_result,
)
from app.services.manifest_parser import ManifestParseError, parse_manifest
from app.services.ocr.fixture_engine import FixtureOCREngine
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
    original_filename: str
    stored_filename: str
    temp_path: Path
    upload_size: int


def _validate_image_upload(upload: UploadFile, temp_dir: Path) -> ValidatedUpload:
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
    dest = job_dir(job_id) / "uploads" / upload.stored_filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    upload.temp_path.replace(dest)
    return dest


def _manifest_item_to_application(item: ManifestItem) -> ColaApplication:
    payload = item.model_dump() if hasattr(item, "model_dump") else item.dict()
    return ColaApplication(**payload)


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


@router.post("/jobs/batch")
def create_batch_job(
    manifest_file: UploadFile = File(...),
    label_images: list[UploadFile] = File(...),
) -> RedirectResponse:
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
    results = list_results(job_id)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"job_id": job_id, "results": results, "manifest": load_manifest(job_id)},
    )


@router.get("/jobs/{job_id}/items/{item_id}", response_class=HTMLResponse)
def item_detail(request: Request, job_id: str, item_id: str):
    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {"job_id": job_id, "result": load_result(job_id, item_id)},
    )


@router.get("/jobs/{job_id}/results.csv")
def csv_export(job_id: str) -> Response:
    csv_text = results_to_csv(list_results(job_id))
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="labels-on-tap-{job_id}.csv"'},
    )
