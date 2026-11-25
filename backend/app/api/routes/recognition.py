from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.dish_recognition import (
    resolve_recognized_dish,
    get_public_dish_recipes,
)
from backend.app.core.config import get_settings
from backend.app.schemas.recognition import (
    AnalysisRoutingResponse,
    ClassPrediction,
    RecognitionResponse,
)
from backend.app.services.food_analysis_router import route_food_analysis
from backend.app.services.image_upload import (
    ImageValidationError,
    validate_image_upload,
)
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


@lru_cache
def get_indian_prediction_provider() -> PredictionProvider:
    settings = get_settings()
    return build_prediction_provider(
        settings.indian_recognition_model_path,
        settings.indian_recognition_labels_path,
        settings.indian_recognition_model_version,
        settings.indian_recognition_confidence_threshold,
        settings.recognition_image_size,
        settings.indian_recognition_temperature,
    )


@router.post("/predict", response_model=RecognitionResponse)
async def predict_food(
    file: UploadFile = File(...),
    model: Literal["food101", "indian"] = "food101",
    db: Session = Depends(get_db),
) -> RecognitionResponse:
    settings = get_settings()

    try:
        image = await validate_image_upload(
            file,
            settings.max_upload_size_mb * 1024 * 1024,
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()

    try:
        provider = (
            get_indian_prediction_provider()
            if model == "indian"
            else get_prediction_provider()
        )
        result = provider.predict(image.content)
    except ModelNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Route downstream analysis using the verified compatibility matrix.
    try:
        routing = route_food_analysis(
            model_source=model,
            predicted_food=result.predicted_food,
            confidence=result.confidence,
            needs_review=result.needs_review,
        )
    except ValueError as exc:
        # A model output absent from the compatibility matrix indicates
        # a model/configuration mismatch, not an invalid user upload.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Recognition output is not compatible with the analysis configuration.",
        ) from exc

    # Preserve existing canonical dish and recipe resolution behaviour.
    canonical_dish = (
        resolve_recognized_dish(db, result.predicted_food, model)
        if result.predicted_food and not result.needs_review
        else None
    )

    associated_recipes = (
        get_public_dish_recipes(db, canonical_dish.id)
        if canonical_dish is not None and not result.needs_review
        else []
    )

    return RecognitionResponse(
        status="needs_review" if result.needs_review else "recognized",
        predicted_food=result.predicted_food,
        confidence=result.confidence,
        needs_review=result.needs_review,
        model_version=result.model_version,
        top_predictions=[
            ClassPrediction(food_label=label, confidence=score)
            for label, score in result.top_predictions
        ],
        message=result.message,
        canonical_dish_id=canonical_dish.id if canonical_dish else None,
        canonical_dish_name=canonical_dish.name if canonical_dish else None,
        associated_recipes=associated_recipes,
        analysis_routing=AnalysisRoutingResponse(
            status=routing.status,
            model_source=routing.model_source,
            food_label=routing.food_label,
            freshness=routing.freshness,
            nutrition=routing.nutrition,
            recipe=routing.recipe,
            fraud=routing.fraud,
            requires_review=routing.requires_review,
            reasons=list(routing.reasons),
        ),
    )