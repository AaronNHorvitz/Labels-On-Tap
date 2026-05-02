"""Tests for public COLA OCR/field evaluation helpers."""

from __future__ import annotations

from pathlib import Path

from app.schemas.ocr import OCRResult
from scripts.cola_etl.evaluation import (
    ApplicationEvaluation,
    FieldEvaluation,
    PanelOCR,
    PublicColaPanel,
    aggregate_text,
    evaluate_field,
    expected_fields,
    field_candidates,
    resolve_work_path,
    write_outputs,
)


def panel_ocr(text: str, *, panel_order: int, image_type: str) -> PanelOCR:
    """Build a small panel OCR fixture."""

    panel = PublicColaPanel(
        ttb_id="26035001000229",
        panel_order=panel_order,
        filename=f"panel-{panel_order}.png",
        image_type=image_type,
        raw_image_path=Path(f"/tmp/panel-{panel_order}.png"),
        source_url="https://example.test/panel.png",
    )
    return PanelOCR(
        panel=panel,
        ocr=OCRResult(
            fixture_id=panel.ttb_id,
            filename=panel.filename,
            full_text=text,
            avg_confidence=0.97,
            blocks=[],
            source="test OCR",
            ocr_ms=10,
            total_ms=10,
        ),
        cache_hit=True,
    )


def test_evaluate_field_searches_all_label_panels() -> None:
    panels = [
        panel_ocr("Decorative crest and batch number", panel_order=1, image_type="Front"),
        panel_ocr("Produced for CORAZON DE REY in Austin, Texas", panel_order=2, image_type="Back"),
    ]

    result = evaluate_field(
        ttb_id="26035001000229",
        field_name="brand_name",
        expected="CORAZÓN DE REY",
        panel_ocrs=panels,
    )

    assert result.verdict == "pass"
    assert result.outcome == "matched"
    assert result.best_panel_order == 2
    assert result.best_panel_type == "Back"


def test_aggregate_text_preserves_panel_boundaries() -> None:
    panels = [
        panel_ocr("Front label text", panel_order=1, image_type="Brand"),
        panel_ocr("Back label government warning", panel_order=2, image_type="Back"),
    ]

    text = aggregate_text(panels)

    assert "[Panel 1: Brand]" in text
    assert "Front label text" in text
    assert "[Panel 2: Back]" in text
    assert "Back label government warning" in text


def test_expected_fields_uses_registry_origin_for_imported_applications() -> None:
    parsed = {
        "application": {
            "brand_name": "CORAZÓN DE REY",
            "fanciful_name": "MEZCAL ARTESANAL JOVEN ESPADÍN",
            "class_type": "MEZCAL FB",
            "imported": True,
        },
        "form_fields": {
            "source_of_product": "Imported",
            "applicant_name_address": "Chupes Finos, DEGA Imports LLC\nAustin\nTX\n78731",
        },
    }

    fields = expected_fields(parsed, {"origin_desc": "MEXICO"})

    assert fields["country_of_origin"] == "MEXICO"
    assert fields["brand_name"] == "CORAZÓN DE REY"
    assert fields["applicant_or_producer"] == "Chupes Finos, DEGA Imports LLC"


def test_field_candidates_adds_alcohol_and_net_contents_variants() -> None:
    assert "45.2% alc/vol" in field_candidates("alcohol_content", "45.2")
    assert "750 ml" in field_candidates("net_contents", "750 MILLILITERS")


def test_resolve_work_path_remaps_host_absolute_paths() -> None:
    resolved = resolve_work_path(
        "/old/host/Labels-On-Tap/data/work/public-cola/raw/images/123/front.png"
    )

    assert str(resolved).endswith("data/work/public-cola/raw/images/123/front.png")


def test_write_outputs_creates_summary_and_csv_files(tmp_path: Path) -> None:
    evaluation = ApplicationEvaluation(
        ttb_id="26035001000229",
        status="approved",
        source_of_product="Imported",
        image_count=2,
        ocr_image_count=2,
        cache_hit_count=2,
        total_ocr_ms=20,
        overall_verdict="pass",
        field_results=[
            FieldEvaluation(
                ttb_id="26035001000229",
                field_name="brand_name",
                expected="CORAZÓN DE REY",
                verdict="pass",
                outcome="matched",
                score=100.0,
                best_panel_order=1,
                best_panel_type="Front",
                best_panel_filename="front.png",
                evidence_text="CORAZON DE REY",
                reviewer_action="No reviewer action needed for this field.",
            )
        ],
    )

    summary = write_outputs(tmp_path, [evaluation])

    assert summary["application_count"] == 1
    assert summary["field_summary"]["brand_name"]["match_rate"] == 1.0
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "field_results.csv").exists()
    assert (tmp_path / "application_results.csv").exists()
