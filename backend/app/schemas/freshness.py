from pydantic import BaseModel, Field


class FreshnessPredictionResponse(BaseModel):
    model_version: str
    category: str
    predicted_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float]
    device: str
    safety_notice: str
