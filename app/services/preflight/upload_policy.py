from __future__ import annotations

from pathlib import Path


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def validate_upload_name(filename: str) -> None:
    path = Path(filename)
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if not suffixes or suffixes[-1] not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Unsupported label image type. Use JPG or PNG.")
    if len(suffixes) > 1:
        raise ValueError("Double-extension uploads are not accepted.")
    if path.name != filename:
        raise ValueError("Upload filename must not include path components.")
