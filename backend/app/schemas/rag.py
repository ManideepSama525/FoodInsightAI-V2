from typing import Any

from pydantic import BaseModel, Field


class NutrientClaimRequest(BaseModel):
    food_id: int = Field(gt=0)
    nutrient_key: str = Field(min_length=1, max_length=100)
    amount: float
    unit: str = Field(min_length=1, max_length=30)
    basis_g: float = Field(gt=0)


class RagQueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=8, ge=1, le=20)
    claim: NutrientClaimRequest | None = None


class RagQueryResponse(BaseModel):
    query: str
    answer: str
    retrieved_count: int
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    verification: dict[str, Any] | None = None