from __future__ import annotations

import secrets
from pathlib import Path
from typing import BinaryIO


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
UPLOAD_CHUNK_BYTES = 1024 * 1024


def validate_upload_name(filename: str) -> None:
    path = Path(filename)
    if "/" in filename or "\\" in filename:
        raise ValueError("Upload filename must not include path components.")
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if not suffixes or suffixes[-1] not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Unsupported label image type. Use JPG or PNG.")
    if len(suffixes) > 1:
        raise ValueError("Double-extension uploads are not accepted.")
    if path.name != filename:
        raise ValueError("Upload filename must not include path components.")


def random_upload_filename(original_filename: str) -> str:
    suffix = Path(original_filename).suffix.lower()
    return f"{secrets.token_hex(16)}{suffix}"


def copy_upload_with_size_limit(source: BinaryIO, dest: Path, max_bytes: int) -> int:
    bytes_written = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as target:
        while True:
            chunk = source.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_bytes:
                raise ValueError(f"Upload exceeds maximum size of {max_bytes} bytes.")
            target.write(chunk)
    return bytes_written


def read_upload_with_size_limit(source: BinaryIO, max_bytes: int) -> bytes:
    content = source.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"Upload exceeds maximum size of {max_bytes} bytes.")
    return content
