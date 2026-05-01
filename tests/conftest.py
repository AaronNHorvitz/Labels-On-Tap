from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_FIXTURE = REPO_ROOT / "data/fixtures/demo/clean_malt_pass.png"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def pytest_sessionstart(session) -> None:
    if DEMO_FIXTURE.exists():
        return

    subprocess.run(
        [sys.executable, "scripts/bootstrap_project.py", "--if-missing"],
        cwd=REPO_ROOT,
        check=True,
    )
