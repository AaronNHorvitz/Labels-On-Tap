from __future__ import annotations

from pathlib import Path


def has_allowed_image_signature(path: Path) -> bool:
    header = path.read_bytes()[:12]
    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
    )
