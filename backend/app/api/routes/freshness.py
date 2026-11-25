from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from backend.app.core.config import get_settings
from backend.app.schemas.freshness import FreshnessPredictionResponse
from backend.app.services.freshness_client import (
    FreshnessServiceError,
    FreshnessServiceUnavailable,
    predict_freshness,
)
from backend.app.services.image_upload import (
    ImageValidationError,
    validate_image_upload,
)


router = APIRouter(prefix="/freshness", tags=["freshness"])


@router.post(
    "/predict",
    response_model=FreshnessPredictionResponse,
)
async def predict_food_freshness(
    category: str = Form(...),
    file: UploadFile = File(...),
) -> FreshnessPredictionResponse:
    settings = get_settings()

    category = category.strip().lower()

    if not category:
        raise HTTPException(
            status_code=422,
            detail="A food category is required.",
        )

    try:
        image = await validate_image_upload(
            file,
            settings.max_upload_size_mb * 1024 * 1024,
        )
    except ImageValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    finally:
        await file.close()

    try:
        result = await predict_freshness(
            service_url=settings.freshness_service_url,
            category=category,
            image_content=image.content,
            media_type=image.media_type,
            filename=f"freshness{image.extension}",
        )
    except FreshnessServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except FreshnessServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    try:
        return FreshnessPredictionResponse.model_validate(result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Freshness service returned an incompatible response.",
        ) from exc
