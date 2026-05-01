"""Server-rendered browser routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import ROOT


router = APIRouter()
templates = Jinja2Templates(directory=str(ROOT / "app/templates"))


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Render the home page with demo, single-upload, and batch-upload forms."""

    return templates.TemplateResponse(request, "index.html")
