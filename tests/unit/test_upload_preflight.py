from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from app.services.preflight.file_signature import (
    has_allowed_image_signature,
    is_pillow_decodable_image,
)
from app.services.preflight.upload_policy import (
    copy_upload_with_size_limit,
    random_upload_filename,
    validate_upload_name,
)


def test_validate_upload_name_accepts_supported_image_names():
    validate_upload_name("label.png")
    validate_upload_name("label.jpg")
    validate_upload_name("label.jpeg")


@pytest.mark.parametrize(
    "filename",
    ["label.pdf", "label.png.php", "../label.png", "nested/label.png", "nested\\label.png"],
)
def test_validate_upload_name_rejects_unsafe_names(filename):
    with pytest.raises(ValueError):
        validate_upload_name(filename)


def test_random_upload_filename_preserves_only_suffix():
    stored = random_upload_filename("clean_malt_pass.PNG")
    assert stored.endswith(".png")
    assert stored != "clean_malt_pass.PNG"
    assert "/" not in stored
    assert "\\" not in stored


def test_copy_upload_with_size_limit_rejects_oversize(tmp_path):
    with pytest.raises(ValueError):
        copy_upload_with_size_limit(BytesIO(b"abcdef"), tmp_path / "upload.png", max_bytes=3)


def test_signature_and_pillow_validation_distinguish_corrupt_png(tmp_path):
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-real-png")

    assert has_allowed_image_signature(corrupt)
    assert not is_pillow_decodable_image(corrupt)
