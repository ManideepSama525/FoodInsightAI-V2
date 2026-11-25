from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.db.session import SessionLocal
from backend.app.models.food import Food, FoodNutrient

SOURCE = "usda_foundation"
SOURCE_URL = "https://fdc.nal.usda.gov/"

# USDA nutrient IDs mapped to the application's existing calculation keys.
STANDARD_KEYS = {
    "1008": "energy_kcal",
    "1003": "protein",
    "1005": "total_carbohydrate",
    "1004": "total_fat",
    "1079": "fiber",
    "2000": "total_sugars",
    "1093": "sodium",
}


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def decimal_value(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        result = Decimal(value.strip())
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def normalized_name(value: str) -> str:
    return " ".join(value.casefold().split())


def import_dataset(data_dir: Path) -> dict:
    required = [
        "food.csv",
        "foundation_food.csv",
        "food_nutrient.csv",
        "nutrient.csv",
        "food_category.csv",
    ]
    for filename in required:
        if not (data_dir / filename).is_file():
            raise FileNotFoundError(f"Missing USDA dataset file: {filename}")

    foundation_ids = {
        str(row["fdc_id"])
        for row in read_csv(data_dir / "foundation_food.csv")
    }

    categories = {
        str(row["id"]): row["description"]
        for row in read_csv(data_dir / "food_category.csv")
    }

    nutrient_definitions = {
        str(row["id"]): {
            "name": row["name"].strip(),
            "unit": row["unit_name"].strip(),
        }
        for row in read_csv(data_dir / "nutrient.csv")
    }

    food_rows = {}
    for row in read_csv(data_dir / "food.csv"):
        fdc_id = str(row["fdc_id"])
        if fdc_id in foundation_ids and row["data_type"] == "foundation_food":
            food_rows[fdc_id] = row

    if len(food_rows) != len(foundation_ids):
        missing = foundation_ids - set(food_rows)
        raise RuntimeError(
            f"Foundation membership mismatch: {len(missing)} IDs missing from food.csv"
        )

    nutrient_rows: dict[str, dict[str, dict]] = {
        fdc_id: {} for fdc_id in foundation_ids
    }

    for row in read_csv(data_dir / "food_nutrient.csv"):
        fdc_id = str(row["fdc_id"])
        nutrient_id = str(row["nutrient_id"])

        if fdc_id not in foundation_ids:
            continue

        definition = nutrient_definitions.get(nutrient_id)
        if not definition:
            continue

        amount = decimal_value(row.get("amount"))
        if amount is None:
            continue

        key = STANDARD_KEYS.get(nutrient_id, f"usda_{nutrient_id}")
        nutrient_rows[fdc_id][key] = {
            "nutrient_key": key,
            "display_name": definition["name"],
            "amount": amount,
            "unit": definition["unit"],
            "basis_g": Decimal("100"),
            "source": SOURCE,
            "source_nutrient_id": nutrient_id,
        }

    stats = {
        "foundation_foods": len(food_rows),
        "foods_inserted": 0,
        "foods_updated": 0,
        "nutrients_inserted": 0,
        "nutrients_updated": 0,
        "nutrients_without_values": 0,
    }

    with SessionLocal() as db:
        existing_foods = {
            food.external_id: food
            for food in db.scalars(
                select(Food)
                .options(selectinload(Food.nutrients))
                .where(
                    Food.source == SOURCE,
                    Food.external_id.in_(list(foundation_ids)),
                )
            ).unique()
        }

        for fdc_id, row in food_rows.items():
            food = existing_foods.get(fdc_id)
            category = categories.get(str(row.get("food_category_id") or ""))

            if food is None:
                food = Food(
                    name=row["description"].strip()[:240],
                    normalized_name=normalized_name(row["description"])[:240],
                    category=category[:120] if category else None,
                    source=SOURCE,
                    external_id=fdc_id,
                    source_url=f"{SOURCE_URL}food-details/{fdc_id}/nutrients",
                    description=(
                        f"USDA FoodData Central Foundation Foods. "
                        f"Publication date: {row.get('publication_date') or 'not specified'}."
                    ),
                )
                db.add(food)
                db.flush()
                stats["foods_inserted"] += 1
            else:
                food.name = row["description"].strip()[:240]
                food.normalized_name = normalized_name(row["description"])[:240]
                food.category = category[:120] if category else None
                food.source_url = f"{SOURCE_URL}food-details/{fdc_id}/nutrients"
                food.description = (
                    f"USDA FoodData Central Foundation Foods. "
                    f"Publication date: {row.get('publication_date') or 'not specified'}."
                )
                stats["foods_updated"] += 1

            existing_nutrients = {
                nutrient.nutrient_key: nutrient for nutrient in food.nutrients
            }

            values = nutrient_rows.get(fdc_id, {})
            if not values:
                stats["nutrients_without_values"] += 1

            for key, data in values.items():
                nutrient = existing_nutrients.get(key)
                if nutrient is None:
                    db.add(FoodNutrient(food_id=food.id, **data))
                    stats["nutrients_inserted"] += 1
                else:
                    nutrient.display_name = data["display_name"]
                    nutrient.amount = data["amount"]
                    nutrient.unit = data["unit"]
                    nutrient.basis_g = data["basis_g"]
                    nutrient.source = SOURCE
                    nutrient.source_nutrient_id = data["source_nutrient_id"]
                    stats["nutrients_updated"] += 1

        db.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Idempotently import USDA Foundation Foods into FoodInsightAI."
    )
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()

    stats = import_dataset(args.data_dir)

    print("\nUSDA FOUNDATION FOODS IMPORT COMPLETE")
    for key, value in stats.items():
        print(f"{key}: {value}")

    print("\nSource: USDA FoodData Central Foundation Foods")
    print("Database transaction committed successfully.")


if __name__ == "__main__":
    main()
