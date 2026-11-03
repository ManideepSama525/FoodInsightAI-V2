from functools import lru_cache

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from backend.app.core.config import get_settings
from backend.app.schemas.recognition import ClassPrediction, RecognitionResponse
from backend.app.services.image_upload import ImageValidationError, validate_image_upload
from backend.app.services.recognition.provider import (
    ModelNotReadyError,
    PredictionProvider,
    build_prediction_provider,
)

router = APIRouter(prefix="/recognition", tags=["recognition"])

@lru_cache
def get_prediction_provider() -> PredictionProvider:
    settings = get_settings()
    return build_prediction_provider(
        settings.recognition_model_path,
        settings.recognition_labels_path,
        settings.recognition_model_version,
        settings.recognition_confidence_threshold,
        settings.recognition_image_size,
    )

@router.post("/predict", response_model=RecognitionResponse)
async def predict_food(file: UploadFile = File(...)) -> RecognitionResponse:
    settings = get_settings()
    try:
        image = await validate_image_upload(file, settings.max_upload_size_mb * 1024 * 1024)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
    try:
        result = get_prediction_provider().predict(image.content)
    except ModelNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RecognitionResponse(
        status="needs_review" if result.needs_review else "recognized",
        predicted_food=result.predicted_food,
        confidence=result.confidence,
        needs_review=result.needs_review,
        model_version=result.model_version,
        top_predictions=[ClassPrediction(food_label=label, confidence=score) for label, score in result.top_predictions],
        message=result.message,
    )
