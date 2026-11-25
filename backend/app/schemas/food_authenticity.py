from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RecipeConsistencyRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    recipe_id: int = Field(gt=0)
    supplied_ingredients: list[
        Annotated[str, Field(min_length=1, max_length=240)]
    ] = Field(min_length=1, max_length=100)


class IngredientResolution(BaseModel):
    input: str
    status: Literal["resolved", "unresolved"]
    reason: str
    food_id: int | None = None
    canonical_name: str | None = None


class RecipeConsistencyCounts(BaseModel):
    matched: int
    missing: int
    unexpected: int
    unresolved_recipe: int
    unresolved_supplied: int


class RecipeConsistencyResponse(BaseModel):
    analysis_type: Literal["RECIPE_INGREDIENT_CONSISTENCY"]
    recipe_id: int
    recipe_name: str
    status: Literal["REVIEW_REQUIRED", "CONSISTENT", "DISCREPANCIES_FOUND"]
    matched_ingredients: list[IngredientResolution]
    missing_expected_ingredients: list[IngredientResolution]
    unexpected_supplied_ingredients: list[IngredientResolution]
    unresolved_recipe_ingredients: list[IngredientResolution]
    unresolved_supplied_ingredients: list[IngredientResolution]
    counts: RecipeConsistencyCounts
    disclaimer: str
