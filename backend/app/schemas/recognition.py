from pydantic import BaseModel, Field

class ClassPrediction(BaseModel):
    food_label: str
    confidence: float = Field(ge=0.0, le=1.0)

class RecognitionResponse(BaseModel):
    status: str
    predicted_food: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    needs_review: bool
    model_version: str | None = None
    top_predictions: list[ClassPrediction] = Field(default_factory=list)
    message: str | None = None
