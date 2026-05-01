#!/usr/bin/env python3
"""
Validate legal corpus consistency.

Checks:
- Every criterion source_ref exists in source-ledger.json.
- Tier 2/Tier 3 rules do not default to Fail.
- Every non-info criterion has at least one fixture or is explicitly documented as fixture_pending.
- Fixture provenance references existing rule IDs and source IDs.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "research/legal-corpus"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    errors: list[str] = []

    sources_doc = load_json(CORPUS / "source-ledger.json")
    criteria_doc = load_json(CORPUS / "matrices/source-backed-criteria.json")
    fixtures_doc = load_json(ROOT / "data/source-maps/fixture-provenance.json")

    sources = sources_doc["sources"]
    criteria = criteria_doc["criteria"]
    fixtures = fixtures_doc["fixtures"]

    source_ids = {s["source_id"] for s in sources}
    rule_ids = {r["rule_id"] for r in criteria}

    for rule in criteria:
        rid = rule["rule_id"]

        for ref in rule.get("source_refs", []):
            if ref not in source_ids:
                errors.append(f"{rid}: missing source_ref {ref}")

        tier = rule.get("confidence_tier", "")
        default_verdict = rule.get("default_verdict", "")

        if tier.startswith("tier_2") or tier.startswith("tier_3"):
            if default_verdict == "fail":
                errors.append(f"{rid}: Tier 2/3 rule must not default to Fail")

        if default_verdict not in {"pass", "fail", "needs_review", "info"}:
            errors.append(f"{rid}: invalid default_verdict {default_verdict}")

        if default_verdict != "info" and not rule.get("fixtures"):
            errors.append(f"{rid}: non-info rule has no fixtures")

    for fixture in fixtures:
        fid = fixture["fixture_id"]

        for rid in fixture.get("rule_ids", []):
            if rid not in rule_ids:
                errors.append(f"{fid}: references missing rule_id {rid}")

        for ref in fixture.get("source_refs", []):
            if ref not in source_ids:
                errors.append(f"{fid}: references missing source_ref {ref}")

    if errors:
        print("Legal corpus validation failed:\n")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("Legal corpus validation passed.")


if __name__ == "__main__":
    main()
