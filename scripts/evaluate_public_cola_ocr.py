#!/usr/bin/env python
"""Evaluate local OCR field matching against public COLA application data.

The command reads only local, gitignored public COLA artifacts under
``data/work/public-cola``. It does not contact the TTB registry.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cola_etl.database import connect
from cola_etl.evaluation import evaluate_application, selected_parsed_paths, write_outputs
from cola_etl.paths import PARSED_OCR_DIR, ensure_public_cola_work_dirs

from app.services.ocr.doctr_engine import DoctrOCREngine


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttb-id", action="append", default=[], help="Evaluate one public COLA TTB ID")
    parser.add_argument("--ttb-id-file", help="File containing one TTB ID per line")
    parser.add_argument("--limit", type=int, default=None, help="Maximum applications to evaluate")
    parser.add_argument(
        "--run-name",
        default="latest",
        help="Output directory name under data/work/public-cola/parsed/ocr/evaluations",
    )
    parser.add_argument("--force-ocr", action="store_true", help="Ignore cached OCR panel JSON")
    parser.add_argument(
        "--cached-only",
        action="store_true",
        help="Use only cached OCR outputs; skip panels/applications without OCR cache",
    )
    return parser.parse_args()


def read_ttb_ids(path: str | None) -> list[str]:
    """Read TTB IDs from a plain text file."""

    if not path:
        return []
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    """Run the public COLA OCR/field matching evaluation."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    ttb_ids = [*args.ttb_id, *read_ttb_ids(args.ttb_id_file)]
    parsed_paths = selected_parsed_paths(ttb_ids=ttb_ids or None, limit=args.limit)
    if not parsed_paths:
        print("No parsed public COLA applications found. Run the public COLA ETL first.")
        return

    engine = DoctrOCREngine()
    evaluations = []
    with connect() as connection:
        for index, parsed_path in enumerate(parsed_paths, start=1):
            print(f"[{index}/{len(parsed_paths)}] evaluate {parsed_path.stem}")
            evaluation = evaluate_application(
                parsed_path=parsed_path,
                connection=connection,
                engine=engine,
                force_ocr=args.force_ocr,
                cached_only=args.cached_only,
            )
            if evaluation is None:
                print("  skipped: no downloaded panels or no OCR output")
                continue
            evaluations.append(evaluation)
            print(
                "  "
                f"{evaluation.overall_verdict}; "
                f"{evaluation.ocr_image_count} image(s); "
                f"{evaluation.cache_hit_count} cache hit(s); "
                f"{evaluation.total_ocr_ms} ms"
            )

    output_dir = PARSED_OCR_DIR / "evaluations" / args.run_name
    summary = write_outputs(output_dir, evaluations)
    print()
    print(f"Wrote evaluation outputs to {output_dir}")
    print(
        "Summary: "
        f"{summary['application_count']} application(s), "
        f"{summary['image_count']} image(s), "
        f"{summary['pass_count']} pass, "
        f"{summary['needs_review_count']} needs_review"
    )


if __name__ == "__main__":
    main()
