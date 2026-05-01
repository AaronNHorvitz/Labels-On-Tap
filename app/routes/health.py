"""Health-check route for local, Docker, and public smoke tests."""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Return a minimal readiness payload.

    Returns
    -------
    dict[str, str]
        Static ``{"status": "ok"}`` response used by curl, Docker/Caddy
        smoke tests, and public deployment checks.
    """

    return {"status": "ok"}
