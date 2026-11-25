import os
from io import BytesIO
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from predictor import ToxiFruitPredictor, MODEL_VERSION

CHECKPOINT = os.getenv(
    "TOXIFRUIT_CHECKPOINT",
    "/app/outputs/food_fraud_toxifruit_vegetable_grouped_letterbox_v2/best_model.pt",
)
MAX_UPLOAD_BYTES = int(os.getenv("TOXIFRUIT_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_IMAGE_PIXELS = 40_000_000

predictor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global predictor
    predictor = ToxiFruitPredictor(CHECKPOINT)
    yield
    predictor = None


app = FastAPI(
    title="FoodInsightAI Fruit and Vegetable Visual Screening",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    loaded = predictor is not None
    return {
        "status": "ready" if loaded else "starting",
        "model_loaded": loaded,
        "model_version": MODEL_VERSION,
        "class_count": 22,
        "device": "cpu",
    }


@app.post("/predict")
async def predict(image: UploadFile = File(...)):
    if predictor is None:
        raise HTTPException(status_code=503, detail="Visual screening model is not ready.")

    content = await image.read(MAX_UPLOAD_BYTES + 1)
    await image.close()

    if not content:
        raise HTTPException(status_code=422, detail="The uploaded image is empty.")

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit.")

    try:
        with Image.open(BytesIO(content)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(
                    status_code=422,
                    detail="Only JPEG, PNG and WEBP images are supported.",
                )

            width, height = source.size
            if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=422,
                    detail="Image dimensions are invalid or exceed the supported limit.",
                )

            source.verify()

    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=422,
            detail="The uploaded file is not a valid supported image.",
        ) from exc

    try:
        return predictor.predict_bytes(content)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Visual screening inference failed.",
        ) from exc
