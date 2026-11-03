from io import BytesIO

import pytest
from fastapi import UploadFile
from PIL import Image
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.services.image_upload import ImageValidationError, validate_image_upload


def test_cors_rejects_wildcard_origin():
    with pytest.raises(ValidationError):
        Settings(cors_origins=["*"])


def test_cors_normalizes_and_deduplicates_origins():
    settings = Settings(cors_origins=[" https://example.com/ ", "https://example.com"])
    assert settings.cors_origins == ["https://example.com"]


@pytest.mark.asyncio
async def test_upload_rejects_mime_type_mismatch():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, format="PNG")
    upload = UploadFile(filename="image.png", file=BytesIO(buffer.getvalue()), headers={"content-type": "image/jpeg"})
    with pytest.raises(ImageValidationError, match="content type"):
        await validate_image_upload(upload, 1024 * 1024)


@pytest.mark.asyncio
async def test_upload_rejects_oversized_content():
    upload = UploadFile(filename="large.png", file=BytesIO(b"x" * 100))
    with pytest.raises(ImageValidationError, match="exceeds"):
        await validate_image_upload(upload, 50)


@pytest.mark.asyncio
async def test_upload_rejects_non_image_bytes():
    upload = UploadFile(filename="not-image.png", file=BytesIO(b"not an image"))
    with pytest.raises(ImageValidationError, match="valid supported image"):
        await validate_image_upload(upload, 1024)


@pytest.mark.asyncio
async def test_upload_accepts_valid_png_and_uses_verified_format():
    buffer = BytesIO()
    Image.new("RGB", (12, 8), "green").save(buffer, format="PNG")
    upload = UploadFile(filename="meal.png", file=BytesIO(buffer.getvalue()), headers={"content-type": "image/png"})
    result = await validate_image_upload(upload, 1024 * 1024)
    assert result.media_type == "image/png"
    assert (result.width, result.height, result.extension) == (12, 8, ".png")
