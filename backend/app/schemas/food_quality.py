from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class FoodQualityProvenance(BaseModel):
    status: Literal["complete", "partial", "invalid"]
    records_assessed: int
    issues: list[str]
    optional_metadata_unavailable: list[str]


class FoodQualityNutrient(BaseModel):
    nutrient_key: str
    display_name: str
    amount: Decimal | None
    unit: str
    basis_g: Decimal | None
    status: Literal[
        "valid",
        "missing",
        "invalid_amount",
        "negative_amount",
        "invalid_basis",
    ]
    source: str
    source_nutrient_id: str | None
    derivation_metadata_available: bool
    provenance_assessment: FoodQualityProvenance


class FoodQualitySummary(BaseModel):
    total_records: int
    available: int
    missing: int
    invalid: int
    coverage_percent: float | None
    invalid_reasons: dict[str, int]


class FoodRegulatoryContext(BaseModel):
    status: Literal["not_assessed"]
    reason: str


class FoodQualityRead(BaseModel):
    food_id: int
    food_name: str
    assessment_status: Literal[
        "assessable",
        "limited_data",
        "data_quality_issues",
        "no_nutrient_data",
    ]
    nutrient_summary: FoodQualitySummary
    food_provenance: FoodQualityProvenance
    nutrients: list[FoodQualityNutrient]
    source_conflicts: list[dict]
    incomparable_measurements: list[dict]
    invalid_evidence: list[dict]
    regulatory_context: FoodRegulatoryContext
    limitations: list[str]
