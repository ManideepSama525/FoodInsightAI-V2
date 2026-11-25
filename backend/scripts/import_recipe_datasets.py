"""Dry-run-first, idempotent importer for FoodInsightAI recipe CSV sources.

Usage inside backend container / project root:
  python -m backend.scripts.import_recipe_datasets --indian-csv PATH --international-csv PATH
  python -m backend.scripts.import_recipe_datasets --indian-csv PATH --international-csv PATH --apply

The importer never imports private recipes, never invents gram weights, and only
creates DishRecipe links for explicit dish-title matches to existing canonical
Dish records. Ingredient mapping is exact normalized-name matching only.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.food import Food
from backend.app.models.dish import Dish, DishRecipe
from backend.app.models.recipe import IngredientAlias, Recipe, RecipeIngredient
from backend.scripts.ingredient_parser import parse_ingredient_cell

SOURCE_CONFIG = {
    "indian_archana": {
        "license": "license_unverified_review_required",
        "attribution": "Dataset compiled from Archana's Kitchen; source repository: IndianFoodDatasetGeneration",
        "url_field": "URL",
    },
    "epicurious_13k": {
        "license": "license_unverified_review_required",
        "attribution": "Recipe text dataset supplied by project owner; original publisher attribution retained where available",
        "url_field": None,
    },
}

# Exact title aliases only. A recipe title must normalize to one of these
# complete strings; mentioning a dish as an ingredient/component is insufficient.
DISH_TITLE_ALIASES = {
    "biryani": {"biryani", "vegetable biryani", "chicken biryani", "mutton biryani"},
    "cholebhature": {"chole bhature", "chole bhatura"},
    "dabeli": {"dabeli", "kutchi dabeli"},
    "dal": {"dal", "daal"},
    "dhokla": {"dhokla", "khaman dhokla", "khaman"},
    "dosa": {"dosa", "masala dosa", "plain dosa", "rava dosa"},
    "jalebi": {"jalebi"},
    "kathiroll": {"kathi roll", "kathi rolls", "kathiroll"},
    "kofta": {"kofta", "malai kofta", "vegetable kofta"},
    "naan": {"naan", "plain naan", "butter naan", "garlic naan"},
    "pakora": {"pakora", "pakoda", "onion pakora", "vegetable pakora"},
    "paneer": {"paneer"},
    "panipuri": {"pani puri", "panipuri", "golgappa"},
    "pavbhaji": {"pav bhaji", "pavbhaji", "cheesy pav bhaji"},
    "vadapav": {"vada pav", "vadapav"},
    # Reviewed recipe-title variants from the 6,871-row Archana dataset.
    # These are explicit title aliases, not fuzzy/substring matching.
    "caesar salad": {"classic caesar salad"},
    "chicken curry": {"kerala chicken curry", "pahadi chicken curry"},
    "chicken wings": {"grilled chicken wings"},
    "croque madame": {"the croque madame sandwich"},
    "french toast": {"masala french toast"},
    "fried rice": {"tofu fried rice", "prawns fried rice"},
    "greek salad": {"classic greek salad"},
    "macaroni and cheese": {"homemade macaroni and cheese"},
    "omelette": {"oats omelette", "spinach omelette"},
    "pancakes": {"nutella pancakes", "potato pancakes"},
    "spaghetti bolognese": {"the best spicy spaghetti bolognese"},
    "spring rolls": {"vegetable spring rolls", "soya spring rolls"},
    "dosa": {"dosa", "masala dosa", "plain dosa", "rava dosa", "egg dosa"},
    "jalebi": {"jalebi", "apple jalebi"},
    "kathiroll": {"kathi roll", "kathi rolls", "kathiroll", "chicken kathi roll"},
    "pakora": {"pakora", "pakoda", "onion pakora", "vegetable pakora", "egg pakora", "palak pakora"},
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_ingredient_alias(value: str) -> str:
    """Normalize ingredient identity without translation or fuzzy guessing."""
    value = unicodedata.normalize("NFKC", value or "").strip()
    value = re.sub(r"^\s*(?:(?:\d+\s*-\s*)?\d+\s*/\s*\d+|\d+(?:\.\d+)?|[Ã‚Â½Ã‚Â¼Ã‚Â¾])\s*", "", value, count=1)
    units = (r"kg|grams?|g|mg|ml|lit(?:er|re)s?|cups?|tablespoons?|tbsp|"
             r"teaspoons?|tsp|ounces?|oz|pounds?|lbs?|cloves?|sprigs?|"
             r"slices?|pieces?|pinch(?:es)?|bunch(?:es)?|inch(?:es)?")
    value = re.sub(r"^\s*(?:" + units + r")\b\.?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*[-–—]\s*(?:finely |thinly |roughly )?(?:chopped|sliced|grated|deseeded|slit|minced|crushed|soaked(?: overnight)?|for cooking|for deep frying|as required|as needed|as per taste|to taste|a pinch|small bunch|tightly packed).*$", "", value, flags=re.I)
    return normalize(value)

def is_compound_ingredient_for_review(raw: str) -> bool:
    """Conservatively exclude combined ingredients and ambiguous alternatives."""
    value = unicodedata.normalize("NFKC", raw or "").casefold().strip()

    if not value:
        return True

    # Multiple ingredients in one source fragment.
    if "," in value:
        return True

    # Explicit alternatives, including parenthetical alternatives.
    if re.search(r"\b(?:or|alternatively|if)\b", value):
        return True

    # Explicit substitutions or ambiguous ingredient forms.
    if re.search(r"\([^)]*\b(?:ghee|paste|powder|chives)\b[^)]*\)", value):
        return True

    # A second quantified ingredient.
    if re.search(
        r"\s[-??]\s*\d+(?:\s*-\s*\d+\s*/\s*\d+|\s*/\s*\d+)?"
        r"\s*(?:kg|g|grams?|ml|cups?|tbsp|tablespoons?|tsp|teaspoons?)\b",
        value,
    ):
        return True

    return False

def build_ingredient_food_index(db: Session) -> tuple[dict[str, Food], dict[str, Food]]:
    """Return exact canonical-name and explicitly approved alias indexes."""
    direct = build_food_index(db)
    aliases = db.scalars(select(IngredientAlias).where(
        IngredientAlias.status == "approved",
        IngredientAlias.food_id.is_not(None),
    )).all()
    approved = {}
    for alias in aliases:
        food = db.get(Food, alias.food_id)
        if food is not None:
            approved[alias.normalized_alias] = food
    return direct, approved


def parse_list_cell(value: str) -> list[str]:
    """Parse Python-list-like CSV cells; otherwise split conservative line items."""
    if not value:
        return []
    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, (list, tuple)):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, SyntaxError):
        pass
    return [x.strip() for x in re.split(r"[\r\n]+", value) if x.strip()]


def normalize_ingredient_display(raw: str) -> str:
    """Return readable ingredient text with quantity and known prep suffix removed."""
    value = unicodedata.normalize("NFKC", raw or "").strip()
    value = re.sub(r"^\s*(?:(?:\d+\s*-\s*)?\d+\s*/\s*\d+|\d+(?:\.\d+)?|[Ã‚Â½Ã‚Â¼Ã‚Â¾])\s*", "", value, count=1)
    units = (r"kg|grams?|g|mg|ml|lit(?:er|re)s?|cups?|tablespoons?|tbsp|"
             r"teaspoons?|tsp|ounces?|oz|pounds?|lbs?|cloves?|sprigs?|"
             r"slices?|pieces?|pinch(?:es)?|bunch(?:es)?|inch(?:es)?")
    value = re.sub(r"^\s*(?:" + units + r")\b\.?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*[-–—]\s*(?:finely |thinly |roughly )?(?:chopped|sliced|grated|deseeded|slit|minced|crushed|soaked(?: overnight)?|for cooking|for deep frying|as required|as needed|as per taste|to taste|a pinch|small bunch|tightly packed).*$", "", value, flags=re.I)
    return value.strip(" -,:" ) or raw.strip()

def parse_quantity(text: str) -> tuple[Decimal | None, str | None, str]:
    """Parse explicit quantities; never convert non-gram units to grams."""
    s = unicodedata.normalize("NFKC", (text or "").strip())

    number = (
        r"(?P<number>"
        r"\d+\s*-\s*\d+\s*/\s*\d+|"
        r"\d+\s+\d+\s*/\s*\d+|"
        r"\d+\s*/\s*\d+|"
        r"\d+(?:\.\d+)?|"
        r"[\u00bd\u00bc\u00be]"
        r")"
    )
    units = (
        r"(?P<unit>kg|grams?|g|mg|ml|l|cups?|tbsp\.?|tablespoons?|"
        r"tsp\.?|teaspoons?|pieces?|cloves?|slices?|pinch(?:es)?|"
        r"sprigs?|ounces?|oz|pounds?|lb|inch(?:es)?)"
    )

    match = re.match(
        r"^\s*" + number + r"\s*" + units + r"\b",
        s,
        flags=re.I,
    )
    if not match:
        return None, None, "unknown"

    token = re.sub(r"\s+", "", match.group("number"))
    fractions = {
        "\u00bd": Decimal("0.5"),
        "\u00bc": Decimal("0.25"),
        "\u00be": Decimal("0.75"),
    }

    try:
        if token in fractions:
            quantity = fractions[token]
        elif "-" in token and "/" in token:
            whole, fraction = token.split("-", 1)
            numerator, denominator = fraction.split("/", 1)
            if int(denominator) == 0:
                return None, None, "unknown"
            quantity = Decimal(whole) + Decimal(numerator) / Decimal(denominator)
        elif "/" in token:
            numerator, denominator = token.split("/", 1)
            if int(denominator) == 0:
                return None, None, "unknown"
            quantity = Decimal(numerator) / Decimal(denominator)
        else:
            quantity = Decimal(token)
    except (InvalidOperation, ZeroDivisionError, ValueError):
        return None, None, "unknown"

    return quantity, match.group("unit").casefold().rstrip("."), "parsed_non_gram"


def indian_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def international_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def adapt_indian(row: dict[str, str]) -> dict[str, Any]:
    title = (row.get("TranslatedRecipeName") or row.get("RecipeName") or "").strip()
    ingredients = parse_ingredient_cell(
        row.get("TranslatedIngredients") or row.get("Ingredients") or "",
        comma_delimited=True,
    )
    servings = row.get("Servings")
    try:
        servings_i = max(1, int(float(servings))) if servings else 1
    except ValueError:
        servings_i = 1
    return {
        "source": "indian_archana",
        "external_id": (row.get("Srno") or "").strip() or hashlib.sha256(title.encode()).hexdigest(),
        "name": title,
        "instructions": (row.get("TranslatedInstructions") or row.get("Instructions") or "").strip() or None,
        "ingredients": ingredients,
        "servings": servings_i,
        "source_url": (row.get("URL") or "").strip() or None,
        "metadata": {
            "original_title": row.get("RecipeName"),
            "original_ingredients": row.get("Ingredients"),
            "original_instructions": row.get("Instructions"),
            "translated_title": row.get("TranslatedRecipeName"),
            "translated_ingredients": row.get("TranslatedIngredients"),
            "translated_instructions": row.get("TranslatedInstructions"),
            "source_dataset": "IndianFoodDatasetCSV.csv",
            "cuisine": row.get("Cuisine"),
            "course": row.get("Course"),
            "diet": row.get("Diet"),
            "prep_time_minutes": row.get("PrepTimeInMins"),
            "cook_time_minutes": row.get("CookTimeInMins"),
            "total_time_minutes": row.get("TotalTimeInMins"),
            "source_row": row.get("Srno"),
        },
    }


def adapt_international(row: dict[str, str]) -> dict[str, Any]:
    title = (row.get("Title") or "").strip()
    ingredients = parse_ingredient_cell(
        row.get("Cleaned_Ingredients") or row.get("Ingredients") or "",
        comma_delimited=False,
    )
    return {
        "source": "epicurious_13k",
        "external_id": (row.get("") or row.get("Unnamed: 0") or "").strip()
            or hashlib.sha256((title + "|" + (row.get("Image_Name") or "")).encode()).hexdigest(),
        "name": title,
        "instructions": (row.get("Instructions") or "").strip() or None,
        "ingredients": ingredients,
        "servings": 1,
        "source_url": None,
        "metadata": {"image_name": row.get("Image_Name")},
    }


def build_food_index(db: Session) -> dict[str, Food]:
    foods = db.scalars(select(Food)).all()
    return {normalize(food.name): food for food in foods if normalize(food.name)}


def build_dish_index(db: Session) -> dict[str, Dish]:
    """Index active canonical Dishes by exact normalized names."""
    dishes = db.scalars(select(Dish).where(Dish.is_active.is_(True))).all()
    return {
        normalize(dish.normalized_name or dish.name): dish
        for dish in dishes
        if normalize(dish.normalized_name or dish.name)
    }


def match_dishes(title: str, dish_index: dict[str, Dish]) -> list[Dish]:
    """Match exact dish titles or explicit, curated title aliases only."""
    title_key = normalize(title)
    if not title_key:
        return []
    # Recipe publishers commonly append "Recipe" to a dish name. Removing
    # only this terminal editorial suffix preserves exact-name semantics.
    candidates = {title_key}
    stripped_title = re.sub(r"\s+recipe(?:\s+in\s+hindi)?$", "", title_key)
    if stripped_title:
        candidates.add(stripped_title)
    # Compare the editorial-suffix-stripped title against aliases too.
    # Example: "Classic Caesar Salad Recipe" -> "classic caesar salad".
    for canonical_key, aliases in DISH_TITLE_ALIASES.items():
        normalized_aliases = {normalize(alias) for alias in aliases}
        if not ({title_key, stripped_title} & normalized_aliases):
            continue
        candidates.update({
            normalize(canonical_key),
            normalize(canonical_key.replace("cholebhature", "chole bhature")),
            normalize(canonical_key.replace("pavbhaji", "pav bhaji")),
            normalize(canonical_key.replace("panipuri", "pani puri")),
            normalize(canonical_key.replace("vadapav", "vada pav")),
            normalize(canonical_key.replace("kathiroll", "kathi roll")),
        })
    matched = {}
    for candidate in candidates:
        dish = dish_index.get(candidate)
        if dish is not None:
            matched[dish.id] = dish
    return list(matched.values())


def load_dish_review(path: Path) -> dict[str, dict[str, str]]:
    """Load and validate human-reviewed Indian recipe associations."""
    decisions = {}
    allowed = {"approved", "rejected", "review_required"}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f)
        required = {
            "source_row_number", "dish_name", "recipe_title",
            "final_decision",
        }
        if not required.issubset(set(rows.fieldnames or [])):
            raise ValueError("Review CSV is missing required columns.")

        for row in rows:
            source_row = (row.get("source_row_number") or "").strip()
            decision = (row.get("final_decision") or "").strip().casefold()
            dish_name = (row.get("dish_name") or "").strip()
            if not source_row or not dish_name or decision not in allowed:
                raise ValueError(f"Invalid review row: {row}")
            if source_row in decisions:
                raise ValueError(f"Duplicate source row in review CSV: {source_row}")
            if row.get("source_record_found", "").strip().casefold() not in {
                "true", "yes", "1"
            }:
                raise ValueError(f"Source record not verified: {source_row}")
            decisions[source_row] = {
                "decision": decision,
                "dish_name": dish_name,
                "recipe_title": (row.get("recipe_title") or "").strip(),
            }

    if len(decisions) != 37:
        raise ValueError(f"Expected 37 reviewed records, found {len(decisions)}")

    counts = {
        decision: sum(x["decision"] == decision for x in decisions.values())
        for decision in allowed
    }
    if counts != {"approved": 34, "rejected": 2, "review_required": 1}:
        raise ValueError(f"Unexpected review decision counts: {counts}")

    return decisions


def import_records(
    db: Session, records, apply: bool,
    dish_reviews: dict[str, dict[str, str]] | None = None,
) -> dict[str, int]:
    """Audit every record in dry-run; only write when apply=True.

    Private recipes are never updated, even if a source identifier collides.
    """
    food_index, approved_alias_index = build_ingredient_food_index(db)
    dish_index = build_dish_index(db)
    counts = {
        "seen": 0, "eligible": 0, "inserted": 0, "updated": 0,
        "ingredients": 0, "mapped_ingredients": 0, "unmapped_ingredients": 0,
        "approved_alias_mappings": 0, "exact_name_mappings": 0,
        "candidate_dish_recipe_links": 0, "created_dish_recipe_links": 0,
        "skipped_missing_title": 0,
        "protected_private_conflicts": 0,
        "review_approved": 0,
        "review_rejected": 0,
        "review_pending": 0,
        "review_rows_matched_dataset": 0,
        "review_rows_missing_dataset": 0,
        "review_approved_dish_links": 0,
    }
    review_rows_seen = set()
    try:
        for record in records:
            counts["seen"] += 1
            title = (record.get("name") or "").strip()[:240]
            if not title:
                counts["skipped_missing_title"] += 1
                continue

            source, external_id = record["source"], record["external_id"]
            existing = db.scalar(select(Recipe).where(
                Recipe.source == source, Recipe.external_id == external_id
            ))
            if existing is not None and existing.user_id is not None:
                counts["protected_private_conflicts"] += 1
                continue

            counts["eligible"] += 1
            if existing is None:
                counts["inserted"] += 1
            else:
                counts["updated"] += 1

            # Dry-run and apply both execute the same parsing/mapping audit.
            parsed_ingredients = []
            for raw_value in record.get("ingredients") or []:
                raw = (raw_value or "").strip()
                if not raw:
                    continue
                quantity, unit, quantity_status = parse_quantity(raw)
                ingredient_name = normalize_ingredient_display(raw)
                alias_key = normalize_ingredient_alias(raw)
                compound_review = is_compound_ingredient_for_review(raw)
                food = None if compound_review else approved_alias_index.get(alias_key)
                mapping_status = (
                    "review_required_compound" if compound_review
                    else ("approved_alias" if food is not None else "unmapped")
                )
                if food is None and not compound_review:
                    food = food_index.get(normalize(ingredient_name))
                    if food is not None:
                        mapping_status = "exact_name"
                counts["ingredients"] += 1
                if food is not None:
                    counts["mapped_ingredients"] += 1
                    if mapping_status == "approved_alias":
                        counts["approved_alias_mappings"] += 1
                    else:
                        counts["exact_name_mappings"] += 1
                else:
                    counts["unmapped_ingredients"] += 1
                parsed_ingredients.append({
                    "raw": raw, "ingredient_name": ingredient_name,
                    "quantity": quantity, "unit": unit,
                    "quantity_status": quantity_status, "food": food,
                    "mapping_status": mapping_status,
                })

            if source == "indian_archana" and dish_reviews is not None:
                source_row = str(
                    (record.get("metadata") or {}).get("source_row") or external_id
                ).strip()
                review = dish_reviews.get(source_row)
                matched_dishes = []

                if review is not None:
                    review_rows_seen.add(source_row)
                    counts["review_rows_matched_dataset"] += 1
                    decision = review["decision"]

                    if decision == "approved":
                        counts["review_approved"] += 1
                        matched_dishes = match_dishes(
                            review["dish_name"], dish_index
                        )
                        if matched_dishes:
                            counts["review_approved_dish_links"] += len(matched_dishes)
                    elif decision == "rejected":
                        counts["review_rejected"] += 1
                    else:
                        counts["review_pending"] += 1
            else:
                matched_dishes = match_dishes(title, dish_index)

            if not apply:
                counts["candidate_dish_recipe_links"] += len(matched_dishes)
                continue

            recipe = existing or Recipe(
                user_id=None, name=title, servings=record["servings"]
            )
            recipe.name = title
            recipe.servings = record["servings"]
            recipe.instructions = (
                record["instructions"][:5000] if record.get("instructions") else None
            )
            recipe.source = source
            recipe.external_id = external_id
            recipe.source_url = record.get("source_url")
            recipe.source_license = SOURCE_CONFIG[source]["license"]
            recipe.source_attribution = SOURCE_CONFIG[source]["attribution"]
            recipe.source_metadata = record.get("metadata") or {}
            if existing:
                recipe.ingredients.clear()

            for item in parsed_ingredients:
                food = item["food"]
                raw = item["raw"]
                recipe.ingredients.append(RecipeIngredient(
                    food_id=food.id if food else None,
                    ingredient_name=item["ingredient_name"][:240] or raw[:240],
                    quantity=item["quantity"],
                    unit=item["unit"],
                    raw_ingredient_text=raw,
                    mapping_status=item["mapping_status"],
                    quantity_status=item["quantity_status"],
                ))
            db.add(recipe)
            db.flush()

            for dish in matched_dishes:
                association = db.scalar(select(DishRecipe).where(
                    DishRecipe.dish_id == dish.id,
                    DishRecipe.recipe_id == recipe.id,
                ))
                if association is None:
                    db.add(DishRecipe(
                        dish_id=dish.id,
                        recipe_id=recipe.id,
                        source=source,
                        provenance={
                            "match_method": "exact_curated_recipe_title",
                            "source_external_id": external_id,
                            "source_url": record.get("source_url"),
                        },
                        is_active=True,
                    ))
                    counts["created_dish_recipe_links"] += 1

            if counts["seen"] % 250 == 0:
                db.flush()

        if dish_reviews is not None:
            counts["review_rows_missing_dataset"] = (
                len(dish_reviews) - len(review_rows_seen)
            )
        if apply:
            db.commit()
        else:
            db.rollback()
        return counts
    except Exception:
        db.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--indian-csv", type=Path)
    parser.add_argument("--international-csv", type=Path)
    parser.add_argument("--dish-review-csv", type=Path)
    parser.add_argument("--apply", action="store_true", help="Commit imports; default is dry-run.")
    args = parser.parse_args()
    if not args.indian_csv and not args.international_csv:
        parser.error("Provide at least one dataset CSV path.")
    def records():
        if args.indian_csv:
            for row in indian_rows(args.indian_csv):
                yield adapt_indian(row)
        if args.international_csv:
            for row in international_rows(args.international_csv):
                yield adapt_international(row)
    dish_reviews = (
        load_dish_review(args.dish_review_csv)
        if args.dish_review_csv else None
    )
    if args.dish_review_csv and not args.indian_csv:
        parser.error("--dish-review-csv requires --indian-csv.")

    db = SessionLocal()
    try:
        result = import_records(
            db, records(), args.apply, dish_reviews=dish_reviews
        )
        print(json.dumps({"mode": "apply" if args.apply else "dry_run", **result}, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()

