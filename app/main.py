"""Application factory for the Labels On Tap FastAPI service.

Notes
-----
This module intentionally keeps application assembly small and explicit. The
prototype uses server-rendered HTML, static local assets, and route modules
instead of a separate frontend build or API gateway.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import JOBS_DIR, ROOT
from app.routes import demo, health, jobs, ui
from app.services.batch_queue import start_worker


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns
    -------
    FastAPI
        Configured application with static assets, route modules, job storage,
        and a browser-friendly HTTP error handler.

    Notes
    -----
    The exception handler returns HTML when the browser asks for HTML and JSON
    otherwise. That keeps upload failures readable in the UI without making API
    clients parse markup.
    """

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Labels On Tap")
    templates = Jinja2Templates(directory=str(ROOT / "app/templates"))
    app.mount("/static", StaticFiles(directory=str(ROOT / "app/static")), name="static")
    app.include_router(health.router)
    app.include_router(ui.router)
    app.include_router(demo.router)
    app.include_router(jobs.router)
    start_worker(jobs.process_queued_batch_job)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(
                request,
                "error.html",
                {"status_code": exc.status_code, "detail": exc.detail},
                status_code=exc.status_code,
            )
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    return app


app = create_app()
