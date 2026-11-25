from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from backend.app.core.config import get_settings

from backend.app.core.auth import get_current_user
from backend.app.models.user import User
from backend.app.schemas.food_fraud import (
    CinnamonFTIRAnalysisRequest,
    CinnamonFTIRAnalysisResponse,
    ProduceVisualScreeningResponse,
)
from backend.app.services.food_fraud import analyze_cinnamon_ftir
from backend.app.services.toxifruit_client import (
    ToxiFruitServiceError,
    ToxiFruitServiceUnavailable,
    screen_produce,
)
from backend.app.services.image_upload import (
    ImageValidationError,
    validate_image_upload,
)


router = APIRouter(
    prefix="/food-fraud",
    tags=["food-fraud"],
)


@router.post(
    "/cinnamon/ftir-analysis",
    response_model=CinnamonFTIRAnalysisResponse,
    summary="Analyze cinnamon powder for FTIR-detected adulteration",
    description=(
        "Uses trained FTIR models to detect adulteration, identify the "
        "adulterant, and estimate its concentration. Requires exactly "
        "2,523 ordered spectral intensity values."
    ),
)
def analyze_cinnamon(
    payload: CinnamonFTIRAnalysisRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> CinnamonFTIRAnalysisResponse:
    try:
        result = analyze_cinnamon_ftir(
            spectral_values=payload.spectral_values,
            sample_id=payload.sample_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cinnamon FTIR models are not available.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cinnamon FTIR model inference is unavailable.",
        ) from exc

    return CinnamonFTIRAnalysisResponse.model_validate(result)


@router.post(
    "/produce/visual-screening",
    response_model=ProduceVisualScreeningResponse,
    summary="Screen produce images for ToxiFruit dataset-associated visual patterns",
    description=(
        "Screens supported fruit and vegetable images against ToxiFruit and VegQual "
        "dataset labels. This is visual screening, not chemical confirmation."
    ),
)
async def screen_produce_image(
    user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> ProduceVisualScreeningResponse:
    settings = get_settings()

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
        result = await screen_produce(
            service_url=settings.toxifruit_service_url,
            image_content=image.content,
            media_type=image.media_type,
            filename=f"produce{image.extension}",
        )
    except ToxiFruitServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ToxiFruitServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    try:
        return ProduceVisualScreeningResponse.model_validate(result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ToxiFruit service returned an incompatible response.",
        ) from exc

