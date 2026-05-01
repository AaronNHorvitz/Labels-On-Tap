"""Image signature and decode validation helpers."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError


def has_allowed_image_signature(path: Path) -> bool:
    """Check whether a file starts with a PNG or JPEG signature.

    Parameters
    ----------
    path:
        Candidate uploaded image path.

    Returns
    -------
    bool
        ``True`` when the magic bytes look like PNG or JPEG.

    Notes
    -----
    This is a pre-decode safety check. It is intentionally followed by Pillow
    decoding because a file can have a plausible header and still be corrupt.
    """

    header = path.read_bytes()[:12]
    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
    )


def is_pillow_decodable_image(path: Path) -> bool:
    """Validate that Pillow can decode the candidate image.

    Parameters
    ----------
    path:
        Candidate uploaded image path.

    Returns
    -------
    bool
        ``True`` when Pillow can open and verify the image.
    """

    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, UnidentifiedImageError):
        return False
    return True
