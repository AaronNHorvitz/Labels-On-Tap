from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_FIXTURE = REPO_ROOT / "data/fixtures/demo/clean_malt_pass.png"


def pytest_sessionstart(session) -> None:
    if DEMO_FIXTURE.exists():
        return

    subprocess.run(
        [sys.executable, "scripts/bootstrap_project.py"],
        cwd=REPO_ROOT,
        check=True,
    )
