from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

@dataclass(frozen=True)
class PreparedImage:
    image: Image.Image
    original_width: int
    original_height: int

def prepare_image(content: bytes, image_size: int = 224) -> PreparedImage:
    if image_size < 32 or image_size > 1024:
        raise ValueError("image_size must be between 32 and 1024")
    try:
        with Image.open(BytesIO(content)) as source:
            oriented = ImageOps.exif_transpose(source)
            rgb = oriented.convert("RGB")
            original_size = rgb.size
            resized = ImageOps.fit(rgb, (image_size, image_size), method=Image.Resampling.BILINEAR)
            return PreparedImage(resized.copy(), original_size[0], original_size[1])
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Unable to decode image for recognition.") from exc
