from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError


def has_allowed_image_signature(path: Path) -> bool:
    header = path.read_bytes()[:12]
    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
    )


def is_pillow_decodable_image(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, UnidentifiedImageError):
        return False
    return True
