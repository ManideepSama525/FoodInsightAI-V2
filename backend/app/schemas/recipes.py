from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

class RecipeIngredientCreate(BaseModel):
    food_id: int
    quantity_g: Decimal = Field(gt=0, le=100000)

class RecipeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    servings: int = Field(default=1, ge=1, le=100)
    instructions: str | None = Field(default=None, max_length=5000)
    ingredients: list[RecipeIngredientCreate] = Field(min_length=1, max_length=100)

class RecipeIngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    food_id: int | None
    ingredient_name: str
    quantity: Decimal
    unit: str

class RecipeRead(BaseModel):
    id: int
    name: str
    servings: int
    instructions: str | None
    ingredients: list[RecipeIngredientRead]
    nutrition_per_recipe: list[dict]
    nutrition_per_serving: list[dict]
