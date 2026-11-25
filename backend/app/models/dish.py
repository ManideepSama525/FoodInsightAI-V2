from sqlalchemy import Boolean, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base import Base


class Dish(Base):
    """Canonical prepared dish predicted by a recognition model."""
    __tablename__ = "dishes"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_dish_normalized_name"),
        Index("ix_dishes_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="curated")
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    recipe_associations: Mapped[list["DishRecipe"]] = relationship(
        back_populates="dish", cascade="all, delete-orphan"
    )


class DishRecipe(Base):
    """Curated association between a canonical Dish and a Recipe."""
    __tablename__ = "dish_recipes"
    __table_args__ = (
        UniqueConstraint("dish_id", "recipe_id", name="uq_dish_recipe_pair"),
        Index("ix_dish_recipes_dish_id", "dish_id"),
        Index("ix_dish_recipes_recipe_id", "recipe_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dish_id: Mapped[int] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    dish: Mapped[Dish] = relationship(back_populates="recipe_associations")
    recipe: Mapped["Recipe"] = relationship()
