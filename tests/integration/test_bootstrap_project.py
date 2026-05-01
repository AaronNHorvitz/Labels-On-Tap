import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_bootstrap_project_if_missing_is_idempotent():
    subprocess.run(
        [sys.executable, "scripts/bootstrap_project.py", "--if-missing"],
        cwd=ROOT,
        check=True,
    )
    expected = json.loads((ROOT / "data/source-maps/expected-results.json").read_text())
    assert "clean_malt_pass" in expected["fixtures"]
    rows = list(csv.DictReader((ROOT / "data/fixtures/demo/batch_manifest.csv").open()))
    assert len(rows) >= 5
