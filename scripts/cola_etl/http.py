"""HTTP helpers for the polite public COLA ETL commands."""

from __future__ import annotations

import random
import time
from pathlib import Path

import httpx


DEFAULT_HEADERS = {
    "User-Agent": "LabelsOnTapResearch/0.1 (+https://www.labelsontap.ai; public COLA fixture research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*,*/*;q=0.8",
}


def polite_sleep(delay_seconds: float, jitter_seconds: float) -> None:
    """Sleep between public requests so the ETL walks instead of stampedes."""

    total = max(0.0, delay_seconds) + random.uniform(0.0, max(0.0, jitter_seconds))
    if total:
        time.sleep(total)


def make_client(timeout: float = 30.0) -> httpx.Client:
    """Create a configured HTTP client for public registry fetches."""

    return httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)


def write_response_bytes(path: Path, response: httpx.Response) -> None:
    """Persist an HTTP response body to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
