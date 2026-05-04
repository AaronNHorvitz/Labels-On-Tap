"""Server-rendered browser routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import MAX_BATCH_ITEMS, ROOT


router = APIRouter()
templates = Jinja2Templates(directory=str(ROOT / "app/templates"))


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Render the public landing page."""

    return templates.TemplateResponse(request, "landing.html")


@router.get("/app", response_class=HTMLResponse)
def app_workspace(request: Request):
    """Render the application workspace with upload and parse controls."""

    return templates.TemplateResponse(request, "index.html", {"max_batch_items": MAX_BATCH_ITEMS})


@router.get("/data-format", response_class=HTMLResponse)
def data_format(request: Request):
    """Render application folder and manifest setup instructions."""

    return templates.TemplateResponse(request, "data_format.html")
