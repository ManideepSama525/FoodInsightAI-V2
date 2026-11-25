from pydantic import BaseModel, ConfigDict, Field


class FoodConcern(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    severity: str = Field(default="unspecified", pattern="^(mild|moderate|severe|unspecified)$")


class FoodProfileUpdate(BaseModel):
    allergies: list[FoodConcern] = Field(default_factory=list, max_length=100)
    intolerances: list[FoodConcern] = Field(default_factory=list, max_length=100)
    dietary_preferences: list[str] = Field(default_factory=list, max_length=30)
    goals: list[str] = Field(default_factory=list, max_length=30)
    disliked_foods: list[str] = Field(default_factory=list, max_length=100)
    cuisine_interests: list[str] = Field(default_factory=list, max_length=30)


class FoodProfileRead(FoodProfileUpdate):
    model_config = ConfigDict(from_attributes=True)
    updated_at: str | None = None


class IngredientEvidence(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    confidence: float | None = Field(default=None, ge=0, le=1)


class FoodSafetyRequest(BaseModel):
    ingredients: list[IngredientEvidence] = Field(min_length=1, max_length=200)


class FoodSafetyMatch(BaseModel):
    ingredient: str
    concern: str
    concern_type: str
    severity: str
    certainty: str
    message: str


class FoodSafetyRead(BaseModel):
    status: str
    safe_to_assume: bool
    matches: list[FoodSafetyMatch]
    unknown_ingredients: list[str]
    disclaimer: str
