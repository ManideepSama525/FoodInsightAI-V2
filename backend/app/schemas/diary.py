from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MealType = Literal["breakfast", "lunch", "dinner", "snack"]


class DiaryEntryCreate(BaseModel):
    food_id: int = Field(gt=0)
    quantity_g: Decimal = Field(gt=0, le=100000)
    meal_type: MealType
    consumed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("consumed_at")
    @classmethod
    def normalize_consumed_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class DiaryEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    food_id: int
    food_name: str
    quantity_g: Decimal
    meal_type: MealType
    consumed_at: datetime
    notes: str | None