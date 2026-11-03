from fastapi import APIRouter, File, HTTPException, UploadFile, status
from backend.app.core.config import get_settings
from backend.app.services.image_upload import ImageValidationError, validate_image_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])

@router.post("/validate-image", status_code=status.HTTP_200_OK)
async def validate_uploaded_image(file: UploadFile = File(...)) -> dict[str, object]:
    settings = get_settings()
    try:
        image = await validate_image_upload(file, settings.max_upload_size_mb * 1024 * 1024)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
    return {"valid": True, "media_type": image.media_type, "width": image.width, "height": image.height, "size_bytes": len(image.content)}
