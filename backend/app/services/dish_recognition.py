"""Exact classifier-label to Dish resolution and public recipe retrieval."""
from __future__ import annotations
import re
import unicodedata
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.models.dish import Dish, DishRecipe
from backend.app.models.food import RecognitionAlias
from backend.app.models.recipe import Recipe, RecipeIngredient


def normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def resolve_recognized_dish(db: Session, label: str, model_source: str) -> Dish | None:
    key = normalize_label(label)
    if not key:
        return None
    rows = db.scalars(
        select(RecognitionAlias).where(
            RecognitionAlias.normalized_label == key,
            RecognitionAlias.is_active.is_(True),
            RecognitionAlias.dish_id.is_not(None),
            RecognitionAlias.model_source.in_([model_source, "any"]),
        ).order_by((RecognitionAlias.model_source == model_source).desc())
    ).all()
    if not rows:
        return None
    best_source = rows[0].model_source
    ids = {row.dish_id for row in rows if row.model_source == best_source}
    if len(ids) != 1:
        return None
    dish = db.get(Dish, next(iter(ids)))
    return dish if dish and dish.is_active else None


def get_public_dish_recipes(db: Session, dish_id: int, limit: int = 5) -> list[dict]:
    rows = db.execute(
        select(DishRecipe, Recipe)
        .join(Recipe, Recipe.id == DishRecipe.recipe_id)
        .where(
            DishRecipe.dish_id == dish_id,
            DishRecipe.is_active.is_(True),
            Recipe.user_id.is_(None),
        )
        .order_by(Recipe.name.asc())
        .limit(limit)
    ).all()
    output = []
    for association, recipe in rows:
        ingredients = db.scalars(
            select(RecipeIngredient)
            .where(RecipeIngredient.recipe_id == recipe.id)
            .order_by(RecipeIngredient.id.asc())
        ).all()
        output.append({
            "recipe_id": recipe.id,
            "recipe_name": recipe.name,
            "servings": recipe.servings,
            "source": recipe.source,
            "source_url": recipe.source_url,
            "source_attribution": recipe.source_attribution,
            "association_source": association.source,
            "association_provenance": association.provenance or {},
            "ingredients": [{
                "ingredient_name": item.ingredient_name,
                "food_id": item.food_id,
                "quantity": float(item.quantity) if item.quantity is not None else None,
                "unit": item.unit,
                "mapping_status": item.mapping_status,
                "quantity_status": item.quantity_status,
            } for item in ingredients],
        })
    return output
