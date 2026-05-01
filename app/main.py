from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import JOBS_DIR, ROOT
from app.routes import demo, health, jobs, ui


def create_app() -> FastAPI:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Labels On Tap")
    templates = Jinja2Templates(directory=str(ROOT / "app/templates"))
    app.mount("/static", StaticFiles(directory=str(ROOT / "app/static")), name="static")
    app.include_router(health.router)
    app.include_router(ui.router)
    app.include_router(demo.router)
    app.include_router(jobs.router)

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
