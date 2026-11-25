"""Conservative recipe ingredient consistency analysis.

This service compares stored recipe ingredients with explicitly
user-confirmed ingredients. It does not detect food fraud or adulteration.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.food import Food
from backend.app.models.recipe import IngredientAlias, Recipe
from backend.scripts.import_recipe_datasets import (
    normalize,
    normalize_ingredient_alias,
    is_compound_ingredient_for_review,
)


DISCLAIMER = (
    "Recipe consistency analysis only. Ingredient discrepancies do not prove "
    "food fraud, adulteration, substitution, or contamination. Recipe variants, "
    "preparation differences, and incomplete user input may explain discrepancies."
)


def build_food_indexes(db: Session) -> tuple[dict[str, Food], dict[str, Food]]:
    """Build exact canonical-name and explicitly approved alias indexes."""
    foods = db.scalars(select(Food).order_by(Food.id)).all()

    canonical = {}
    for food in foods:
        key = normalize(food.normalized_name or food.name)
        if key:
            canonical.setdefault(key, food)

    aliases = db.scalars(
        select(IngredientAlias).where(
            IngredientAlias.status == "approved",
            IngredientAlias.food_id.is_not(None),
        )
    ).all()

    approved = {}
    for alias in aliases:
        food = db.get(Food, alias.food_id)
        if food is not None:
            approved.setdefault(alias.normalized_alias, food)

    return canonical, approved


def resolve_ingredient(
    raw: str,
    canonical_index: dict[str, Food],
    approved_alias_index: dict[str, Food],
) -> dict:
    """Resolve one ingredient without fuzzy matching or candidate approval."""
    value = (raw or "").strip()

    if not value:
        return {
            "input": raw,
            "status": "unresolved",
            "reason": "EMPTY_INPUT",
            "food_id": None,
            "canonical_name": None,
        }

    if is_compound_ingredient_for_review(value):
        return {
            "input": value,
            "status": "unresolved",
            "reason": "COMPOUND_OR_AMBIGUOUS_INGREDIENT",
            "food_id": None,
            "canonical_name": None,
        }

    alias_key = normalize_ingredient_alias(value)
    if not alias_key:
        return {
            "input": value,
            "status": "unresolved",
            "reason": "UNPARSEABLE_INGREDIENT",
            "food_id": None,
            "canonical_name": None,
        }

    food = approved_alias_index.get(alias_key)
    if food is not None:
        return {
            "input": value,
            "status": "resolved",
            "reason": "APPROVED_ALIAS",
            "food_id": food.id,
            "canonical_name": food.name,
        }

    food = canonical_index.get(alias_key)
    if food is not None:
        return {
            "input": value,
            "status": "resolved",
            "reason": "EXACT_CANONICAL_NAME",
            "food_id": food.id,
            "canonical_name": food.name,
        }

    return {
        "input": value,
        "status": "unresolved",
        "reason": "NO_APPROVED_EXACT_MAPPING",
        "food_id": None,
        "canonical_name": None,
    }


def analyze_recipe_consistency(
    db: Session,
    recipe: Recipe,
    supplied_ingredients: list[str],
) -> dict:
    """Compare recipe ingredients with explicitly supplied ingredients."""
    canonical_index, approved_alias_index = build_food_indexes(db)

    expected = []
    for item in recipe.ingredients:
        if item.food_id is not None:
            food = db.get(Food, item.food_id)
            if food is not None:
                expected.append({
                    "input": item.ingredient_name,
                    "status": "resolved",
                    "reason": "STORED_CANONICAL_FOOD_ID",
                    "food_id": food.id,
                    "canonical_name": food.name,
                })
                continue

        expected.append(
            resolve_ingredient(
                item.ingredient_name,
                canonical_index,
                approved_alias_index,
            )
        )

    supplied = [
        resolve_ingredient(value, canonical_index, approved_alias_index)
        for value in supplied_ingredients
    ]

    expected_ids = {
        item["food_id"]
        for item in expected
        if item["status"] == "resolved"
    }
    supplied_ids = {
        item["food_id"]
        for item in supplied
        if item["status"] == "resolved"
    }

    matched_ids = expected_ids & supplied_ids
    missing_ids = expected_ids - supplied_ids
    unexpected_ids = supplied_ids - expected_ids

    def entries_for_ids(items, ids):
        return [
            item for item in items
            if item["status"] == "resolved" and item["food_id"] in ids
        ]

    return {
        "analysis_type": "RECIPE_INGREDIENT_CONSISTENCY",
        "recipe_id": recipe.id,
        "recipe_name": recipe.name,
        "status": (
            "REVIEW_REQUIRED"
            if any(item["status"] == "unresolved" for item in expected + supplied)
            else "CONSISTENT"
            if not missing_ids and not unexpected_ids
            else "DISCREPANCIES_FOUND"
        ),
        "matched_ingredients": entries_for_ids(expected, matched_ids),
        "missing_expected_ingredients": entries_for_ids(expected, missing_ids),
        "unexpected_supplied_ingredients": entries_for_ids(supplied, unexpected_ids),
        "unresolved_recipe_ingredients": [
            item for item in expected if item["status"] == "unresolved"
        ],
        "unresolved_supplied_ingredients": [
            item for item in supplied if item["status"] == "unresolved"
        ],
        "counts": {
            "matched": len(matched_ids),
            "missing": len(missing_ids),
            "unexpected": len(unexpected_ids),
            "unresolved_recipe": sum(
                item["status"] == "unresolved" for item in expected
            ),
            "unresolved_supplied": sum(
                item["status"] == "unresolved" for item in supplied
            ),
        },
        "disclaimer": DISCLAIMER,
    }
