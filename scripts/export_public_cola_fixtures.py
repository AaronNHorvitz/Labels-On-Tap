#!/usr/bin/env python
"""Export parsed public COLA records into small committed fixture folders."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from cola_etl.database import connect
from cola_etl.paths import PUBLIC_COLA_FIXTURE_DIR, ensure_public_cola_work_dirs


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttb-id", action="append", required=True, help="TTB ID to export")
    parser.add_argument("--force", action="store_true", help="Overwrite existing fixture folder")
    return parser.parse_args()


def main() -> None:
    """Export curated official public COLA fixture directories."""

    args = parse_args()
    ensure_public_cola_work_dirs()
    with connect() as connection:
        for ttb_id in args.ttb_id:
            form = connection.execute(
                "SELECT * FROM form_fetches WHERE ttb_id = ?", (ttb_id,)
            ).fetchone()
            if not form or not form["parsed_json_path"]:
                print(f"skip {ttb_id}: parse it before exporting")
                continue

            target_dir = PUBLIC_COLA_FIXTURE_DIR / ttb_id
            if target_dir.exists() and not args.force:
                print(f"skip existing fixture {target_dir}")
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            labels_dir = target_dir / "labels"
            labels_dir.mkdir(exist_ok=True)

            parsed = json.loads(Path(form["parsed_json_path"]).read_text(encoding="utf-8"))
            if form["raw_html_path"]:
                shutil.copy2(form["raw_html_path"], target_dir / "source.html")

            copied_labels: list[str] = []
            rows = connection.execute(
                "SELECT * FROM attachments WHERE ttb_id = ? ORDER BY panel_order", (ttb_id,)
            ).fetchall()
            for row in rows:
                if not row["raw_image_path"]:
                    continue
                source = Path(row["raw_image_path"])
                destination = labels_dir / source.name
                shutil.copy2(source, destination)
                copied_labels.append(str(Path("labels") / destination.name))

            (target_dir / "application.json").write_text(
                json.dumps(parsed["application"], indent=2) + "\n",
                encoding="utf-8",
            )
            (target_dir / "expected.json").write_text(
                json.dumps(
                    {
                        "fixture_id": f"public_cola_{ttb_id}",
                        "source_ttb_id": ttb_id,
                        "overall_verdict": "needs_review",
                        "checked_rule_ids": [],
                        "triggered_rule_ids": [],
                        "top_reason": (
                            "Official public COLA fixture exported for OCR/form matching "
                            "research. Expected verdict should be finalized after OCR review."
                        ),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (target_dir / "provenance.json").write_text(
                json.dumps(
                    {
                        "source_type": "ttb_public_cola_registry",
                        "ttb_id": ttb_id,
                        "source_url": parsed.get("source_url"),
                        "raw_html_path": form["raw_html_path"],
                        "parsed_json_path": form["parsed_json_path"],
                        "registry_status": parsed["form_fields"].get("status"),
                        "exported_labels": copied_labels,
                        "used_for": [
                            "official public application structure",
                            "label image OCR realism",
                            "field-to-label comparison fixture curation",
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"exported {ttb_id} -> {target_dir}")


if __name__ == "__main__":
    main()
