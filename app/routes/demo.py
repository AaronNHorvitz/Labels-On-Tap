"""One-click deterministic demo routes.

Notes
-----
The demo routes create normal filesystem-backed jobs using generated fixture
images and fixture OCR ground truth. This keeps the evaluator walkthrough
stable while preserving the same result storage and rule-engine path used by
manual uploads.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.config import DEMO_FIXTURE_DIR
from app.services.fixture_loader import DEMO_SCENARIOS, load_application
from app.services.job_store import add_manifest_item, create_job, save_upload, write_result
from app.services.ocr.fixture_engine import FixtureOCREngine
from app.services.rules.registry import verify_label


router = APIRouter()
ocr_engine = FixtureOCREngine()


def run_fixture_job(scenario: str) -> str:
    """Create a job from a named fixture scenario.

    Parameters
    ----------
    scenario:
        Scenario key from ``DEMO_SCENARIOS`` such as ``"clean"`` or
        ``"batch"``.

    Returns
    -------
    str
        Newly-created job identifier.

    Raises
    ------
    HTTPException
        Raised with status 404 when the scenario is unknown.
    """

    fixture_ids = DEMO_SCENARIOS.get(scenario)
    if not fixture_ids:
        raise HTTPException(status_code=404, detail="Unknown demo scenario")

    job_id = create_job(label=f"{scenario} demo")
    for fixture_id in fixture_ids:
        application = load_application(fixture_id)
        source_image = DEMO_FIXTURE_DIR / application.filename
        save_upload(job_id, source_image, application.filename)
        ocr = ocr_engine.run(source_image, fixture_id=fixture_id)
        result = verify_label(job_id, fixture_id, application, ocr)
        write_result(result)
        add_manifest_item(
            job_id,
            {
                "item_id": fixture_id,
                "filename": application.filename,
                "fixture_id": fixture_id,
            },
        )
    return job_id


@router.get("/demo/{scenario}")
def demo(scenario: str) -> RedirectResponse:
    """Run a fixture demo and redirect to the result page."""

    job_id = run_fixture_job(scenario)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
