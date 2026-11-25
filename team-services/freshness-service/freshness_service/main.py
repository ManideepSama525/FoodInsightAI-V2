from contextlib import asynccontextmanager
from io import BytesIO
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from freshness_service.model_loader import FreshnessInferenceEngine
from freshness_service.preprocessing import preprocess_image
from freshness_service.schemas import (
    FreshnessHealthResponse,
    FreshnessPredictionResponse,
)


MODEL_VERSION = "freshness-v1"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SAFETY_NOTICE = (
    "This is an image-based freshness estimate, not a food-safety "
    "certification. It cannot detect pathogens, toxins, or chemical "
    "contamination. Do not use it alone to decide whether food is safe."
)

engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    engine = FreshnessInferenceEngine()
    yield
    engine = None


app = FastAPI(
    title="FoodInsightAI Freshness Inference API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=FreshnessHealthResponse)
def health():
    loaded = engine is not None

    return FreshnessHealthResponse(
        status="ready" if loaded else "not_ready",
        model_loaded=loaded,
        model_version=MODEL_VERSION,
        device=str(engine.device) if loaded else None,
        category_count=len(engine.category_names) if loaded else 0,
    )


@app.post(
    "/predict",
    response_model=FreshnessPredictionResponse,
)
def predict(
    category: str = Form(...),
    image: UploadFile = File(...),
):
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Freshness model is not loaded",
        )

    category = category.strip().lower()

    if category not in engine.category_to_idx:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported category. Supported categories: "
                   f"{engine.category_names}",
        )

    if image.content_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
    }:
        raise HTTPException(
            status_code=415,
            detail="Upload a JPEG, PNG, WEBP, or BMP image",
        )

    try:
        raw = image.file.read(MAX_IMAGE_BYTES + 1)

        if not raw:
            raise HTTPException(status_code=400, detail="Empty image")

        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Image exceeds the 10 MB upload limit",
            )

        with Image.open(BytesIO(raw)) as source:
            source.verify()

        with Image.open(BytesIO(raw)) as source:
            source.load()
            tensor = preprocess_image(source)

    except HTTPException:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid or unsupported image file",
        )

    try:
        result = engine.predict(tensor, category)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return FreshnessPredictionResponse(
        model_version=MODEL_VERSION,
        **result,
        device=str(engine.device),
        safety_notice=SAFETY_NOTICE,
    )
