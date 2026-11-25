import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CinnamonFTIRAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    spectral_values: list[float] = Field(
        min_length=2523,
        max_length=2523,
        description="Exactly 2,523 FTIR intensity values in the trained model's feature order.",
    )

    @field_validator("spectral_values")
    @classmethod
    def validate_spectral_values(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("All FTIR spectral values must be finite numbers.")
        return values


class ProduceVisualScreeningResponse(BaseModel):
    predicted_class: str
    category: Literal["fruit", "vegetable"]
    fruit: Literal["Apple", "Banana", "Malta", "Mango"] | None = None
    vegetable: str | None = None
    condition: Literal["fresh_control", "formalin_treated"] | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float]
    model: str
    model_version: str
    interpretation: str

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(cls, values: dict[str, float]) -> dict[str, float]:
        if not values or not all(
            math.isfinite(value) and 0.0 <= value <= 1.0
            for value in values.values()
        ):
            raise ValueError("Class scores must be finite values between 0 and 1.")
        return values

class CinnamonFTIRAnalysisResponse(BaseModel):
    sample_id: str | None
    food: Literal["Cinnamon powder"] = "Cinnamon powder"
    adulteration_status: Literal["Pure_Cinnamon", "Adulterated"]
    is_adulterated: bool
    adulterant_type: Literal["Peanut", "Walnut", "Wood_Dust"] | None
    estimated_concentration_percent: float
    concentration_unit: Literal["percent"] = "percent"
    model_version: str = "cinnamon-ftir-v1"
    validation_note: str

