from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class NutrientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nutrient_key: str
    display_name: str
    amount: Decimal | None
    unit: str
    basis_g: Decimal
    source: str


class FoodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str | None
    source: str
    external_id: str | None
    source_url: str | None
    nutrients: list[NutrientRead]


class FoodSearchResult(BaseModel):
    fdc_id: int | None
    description: str | None
    data_type: str | None = None
    brand_owner: str | None = None
    brand_name: str | None = None
    food_category: str | None = None
    publication_date: str | None = None


class FoodSearchResponse(BaseModel):
    query: str
    count: int
    results: list[FoodSearchResult]
