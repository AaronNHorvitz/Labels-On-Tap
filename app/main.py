from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import JOBS_DIR, ROOT
from app.routes import demo, health, jobs, ui


def create_app() -> FastAPI:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Labels On Tap")
    app.mount("/static", StaticFiles(directory=str(ROOT / "app/static")), name="static")
    app.include_router(health.router)
    app.include_router(ui.router)
    app.include_router(demo.router)
    app.include_router(jobs.router)
    return app


app = create_app()
