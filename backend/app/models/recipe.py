from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_recipe_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    servings: Mapped[int] = mapped_column(default=1)
    instructions: Mapped[str | None] = mapped_column(String(5000))
    source: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_license: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_attribution: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    food_associations: Mapped[list["FoodRecipe"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id"), nullable=True)
    ingredient_name: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    raw_ingredient_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unmapped")
    quantity_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


class FoodRecipe(Base):
    """Curated association between a canonical food and a recipe."""
    __tablename__ = "food_recipes"
    __table_args__ = (
        UniqueConstraint("food_id", "recipe_id", name="uq_food_recipe_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recipe: Mapped[Recipe] = relationship(back_populates="food_associations")
    food: Mapped["Food"] = relationship(back_populates="recipe_associations")


class IngredientAlias(Base):
    """Controlled recipe-ingredient synonym mapped to a canonical USDA Food.

    Review candidates have no active food mapping until explicitly approved.
    RecognitionAlias remains a separate model for classifier labels.
    """
    __tablename__ = "ingredient_aliases"
    __table_args__ = (
        UniqueConstraint("normalized_alias", name="uq_ingredient_alias_normalized"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=True, index=True
    )
    candidate_food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="review_required", index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="manual_review")
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
