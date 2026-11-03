from io import BytesIO
import pytest
from fastapi import UploadFile
from PIL import Image
from backend.app.services.image_upload import ImageValidationError, validate_image_upload

def make_png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (12, 8), color="white").save(buffer, format="PNG")
    return buffer.getvalue()

@pytest.mark.anyio
async def test_accepts_valid_png() -> None:
    upload = UploadFile(filename="meal.png", file=BytesIO(make_png()), headers={"content-type": "image/png"})
    result = await validate_image_upload(upload, 1024 * 1024)
    assert result.media_type == "image/png"
    assert (result.width, result.height) == (12, 8)

@pytest.mark.anyio
async def test_rejects_mime_mismatch() -> None:
    upload = UploadFile(filename="meal.png", file=BytesIO(make_png()), headers={"content-type": "image/jpeg"})
    with pytest.raises(ImageValidationError, match="content type"):
        await validate_image_upload(upload, 1024 * 1024)

@pytest.mark.anyio
async def test_rejects_oversized_file() -> None:
    upload = UploadFile(filename="large.png", file=BytesIO(make_png()))
    with pytest.raises(ImageValidationError, match="exceeds"):
        await validate_image_upload(upload, 10)
