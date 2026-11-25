from pydantic import BaseModel, Field


class ClassPrediction(BaseModel):
    food_label: str
    confidence: float = Field(ge=0.0, le=1.0)


class RecognizedIngredient(BaseModel):
    ingredient_name: str
    food_id: int | None = None
    quantity: float | None = None
    unit: str | None = None
    mapping_status: str
    quantity_status: str


class AssociatedRecipe(BaseModel):
    recipe_id: int
    recipe_name: str
    servings: int
    source: str | None = None
    source_url: str | None = None
    source_attribution: str | None = None
    association_source: str
    association_provenance: dict = Field(default_factory=dict)
    ingredients: list[RecognizedIngredient] = Field(default_factory=list)


class AnalysisRoutingResponse(BaseModel):
    status: str
    model_source: str
    food_label: str | None = None
    freshness: str
    nutrition: str
    recipe: str
    fraud: str
    requires_review: bool
    reasons: list[str] = Field(default_factory=list)


class RecognitionResponse(BaseModel):
    status: str
    predicted_food: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    needs_review: bool
    model_version: str | None = None
    top_predictions: list[ClassPrediction] = Field(default_factory=list)
    message: str | None = None

    # Deprecated compatibility fields; kept nullable for existing clients.
    canonical_food_id: int | None = None
    canonical_food_name: str | None = None
    canonical_dish_id: int | None = None
    canonical_dish_name: str | None = None

    associated_recipes: list[AssociatedRecipe] = Field(default_factory=list)

    # New optional analysis-routing information.
    analysis_routing: AnalysisRoutingResponse | None = None