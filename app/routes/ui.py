"""Server-rendered browser routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import MAX_BATCH_ITEMS, ROOT
from app.routes.jobs import _job_comparison_payload
from app.services.job_store import list_results, load_manifest
from app.services.batch_queue import load_queue_status
from app.services.rules.strict_warning import CANONICAL_WARNING


router = APIRouter()
templates = Jinja2Templates(directory=str(ROOT / "app/templates"))
LAST_ACTUAL_JOB_COOKIE = "labels_on_tap_last_actual_job"


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Render the public landing page."""

    return templates.TemplateResponse(request, "landing.html")


@router.get("/app", response_class=HTMLResponse)
def app_workspace(request: Request):
    """Render the application workspace with upload and parse controls."""

    actual_job_id = request.cookies.get(LAST_ACTUAL_JOB_COOKIE, "")
    context: dict[str, Any] = {
        "max_batch_items": MAX_BATCH_ITEMS,
        "actual_job_id": "",
        "actual_applications": [],
        "comparison_rows": {},
    }
    if actual_job_id:
        try:
            manifest = load_manifest(actual_job_id)
            results = list_results(actual_job_id)
            queue_status = load_queue_status(actual_job_id)
            context.update(
                {
                    "actual_job_id": actual_job_id,
                    "actual_applications": _actual_applications_from_job(actual_job_id, manifest, queue_status),
                    "comparison_rows": _job_comparison_payload(results),
                }
            )
        except Exception:
            context["actual_job_id"] = ""
    return templates.TemplateResponse(request, "index.html", context)


@router.post("/app/reset")
def reset_app_workspace():
    """Forget the last uploaded LOT Actual job for this browser."""

    response = RedirectResponse(url="/app", status_code=303)
    response.delete_cookie(LAST_ACTUAL_JOB_COOKIE)
    return response


@router.get("/data-format", response_class=HTMLResponse)
def data_format(request: Request):
    """Render application folder and manifest setup instructions."""

    return templates.TemplateResponse(request, "data_format.html")


def _actual_applications_from_job(job_id: str, manifest: dict[str, Any], queue_status: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build browser application records from a durable LOT Actual upload job."""

    payload_items = queue_status.get("payload", {}).get("items", []) if queue_status else []
    application_by_id = {
        str(payload.get("item_id") or payload.get("item", {}).get("fixture_id") or payload.get("item", {}).get("filename")): payload.get("item", {})
        for payload in payload_items
        if isinstance(payload, dict)
    }
    applications: list[dict[str, Any]] = []
    for item in manifest.get("items", []):
        item_id = str(item.get("item_id") or item.get("fixture_id") or item.get("filename") or "")
        stored_filenames = item.get("stored_filenames") or [item.get("stored_filename")]
        images = [
            {"url": f"/jobs/{job_id}/uploads/{filename}"}
            for filename in stored_filenames
            if filename
        ]
        if not item_id or not images:
            continue
        application = application_by_id.get(item_id, {})
        applications.append(
            {
                "id": str(item.get("filename") or item_id),
                "result_id": item_id,
                "images": images,
                "actual_rows": _actual_truth_rows(application),
            }
        )
    return applications


def _actual_truth_rows(item: dict[str, Any]) -> list[dict[str, str]]:
    """Return application truth rows for a server-restored LOT Actual job."""

    product_type = str(item.get("product_type") or "").replace("_", " ").title()
    imported = bool(item.get("imported"))
    return [
        {"label": "Brand name", "actual": str(item.get("brand_name") or "Not provided")},
        {"label": "Fanciful name", "actual": str(item.get("fanciful_name") or "Not provided")},
        {"label": "Product type", "actual": product_type or "Not provided"},
        {"label": "Class/type", "actual": str(item.get("class_type") or "Not provided")},
        {"label": "Alcohol content", "actual": str(item.get("alcohol_content") or "Not provided")},
        {"label": "Net contents", "actual": str(item.get("net_contents") or "Not provided")},
        {"label": "Bottler / producer", "actual": str(item.get("bottler_producer_name_address") or "Not provided")},
        {"label": "Imported", "actual": "Yes" if imported else "No"},
        {"label": "Country of origin", "actual": str(item.get("country_of_origin") or "Not provided")},
        {"label": "Government warning text", "actual": CANONICAL_WARNING},
        {"label": "Government warning heading", "actual": "GOVERNMENT WARNING:"},
        {"label": "Government warning boldness", "actual": "Bold heading required"},
    ]
