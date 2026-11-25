from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        Index("ix_foods_name", "name"),
        Index("ix_foods_source_external_id", "source", "external_id"),
        UniqueConstraint("source", "external_id", name="uq_food_source_external_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    nutrients: Mapped[list["FoodNutrient"]] = relationship(back_populates="food", cascade="all, delete-orphan")
    recipe_associations: Mapped[list["FoodRecipe"]] = relationship(back_populates="food")


class FoodNutrient(Base):
    __tablename__ = "food_nutrients"
    __table_args__ = (UniqueConstraint("food_id", "nutrient_key", name="uq_food_nutrient_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"), index=True)
    nutrient_key: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 5), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    basis_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("100"))
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_nutrient_id: Mapped[str | None] = mapped_column(String(100))
    derivation_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    derivation_description: Mapped[str | None] = mapped_column(String(160), nullable=True)
    derivation_source_description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    food: Mapped[Food] = relationship(back_populates="nutrients")


class RecognitionAlias(Base):
    """A curated classifier label targeting exactly one canonical Food or Dish."""

    __tablename__ = "recognition_aliases"
    __table_args__ = (
        UniqueConstraint(
            "model_source", "normalized_label",
            name="uq_recognition_alias_model_label",
        ),
        Index("ix_recognition_alias_normalized_label", "normalized_label"),
        CheckConstraint(
            "(food_id IS NOT NULL AND dish_id IS NULL) OR "
            "(food_id IS NULL AND dish_id IS NOT NULL)",
            name="ck_recognition_alias_exactly_one_target",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dish_id: Mapped[int | None] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(240), nullable=False)
    model_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="any", server_default="any"
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    provenance: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    food: Mapped[Food | None] = relationship()
    dish: Mapped["Dish | None"] = relationship()
