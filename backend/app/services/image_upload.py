from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import warnings
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    media_type: str
    extension: str
    width: int
    height: int


class ImageValidationError(ValueError):
    pass


async def validate_image_upload(upload: UploadFile, max_size_bytes: int) -> ValidatedImage:
    content = await upload.read(max_size_bytes + 1)
    if not content:
        raise ImageValidationError("The uploaded file is empty.")
    if len(content) > max_size_bytes:
        raise ImageValidationError(f"Image exceeds the {max_size_bytes // (1024 * 1024)} MB limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image_format, width, height = image.format, *image.size
                image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError("The uploaded file is not a valid supported image.") from exc
    if image_format not in ALLOWED_FORMATS:
        raise ImageValidationError("Only JPEG, PNG and WEBP images are supported.")
    expected_type = ALLOWED_FORMATS[image_format]
    if upload.content_type and upload.content_type != expected_type:
        raise ImageValidationError("The declared content type does not match the image content.")
    if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
        raise ImageValidationError("Image dimensions are invalid or exceed the supported limit.")
    extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
    return ValidatedImage(content, expected_type, extension, width, height)


def store_validated_image(image: ValidatedImage, destination: Path) -> str:
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{image.extension}"
    (destination / filename).write_bytes(image.content)
    return filename
