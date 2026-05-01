from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import ROOT
from app.schemas.application import ColaApplication
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
from app.services.ocr.fixture_engine import FixtureOCREngine
from app.services.preflight.file_signature import has_allowed_image_signature
from app.services.preflight.upload_policy import validate_upload_name
from app.services.rules.registry import verify_label


router = APIRouter()
templates = Jinja2Templates(directory=str(ROOT / "app/templates"))
ocr_engine = FixtureOCREngine()


@router.post("/jobs")
def create_single_job(
    brand_name: str = Form(...),
    product_type: str = Form("malt_beverage"),
    class_type: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    label_image: UploadFile = File(...),
) -> RedirectResponse:
    if not label_image.filename:
        raise HTTPException(status_code=400, detail="Missing upload filename")
    try:
        validate_upload_name(label_image.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = create_job(label="single upload")
    uploads_dir = job_dir(job_id) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(label_image.filename).name
    dest = uploads_dir / safe_name
    with dest.open("wb") as f:
        shutil.copyfileobj(label_image.file, f)
    if not has_allowed_image_signature(dest):
        raise HTTPException(status_code=400, detail="Upload does not match JPG/PNG signature")

    application = ColaApplication(
        filename=safe_name,
        product_type=product_type,
        brand_name=brand_name,
        class_type=class_type,
        alcohol_content=alcohol_content,
        net_contents=net_contents,
    )
    item_id = dest.stem
    ocr = ocr_engine.run(dest, fixture_id=item_id)
    result = verify_label(job_id, item_id, application, ocr)
    write_result(result)
    add_manifest_item(job_id, {"item_id": item_id, "filename": safe_name})
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
