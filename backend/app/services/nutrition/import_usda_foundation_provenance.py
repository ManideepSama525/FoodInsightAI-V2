from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import inspect, select
from sqlalchemy.orm import selectinload

from backend.app.db.session import SessionLocal
from backend.app.models.food import Food

SOURCE = "usda_foundation"

PROVENANCE_FIELDS = (
    "derivation_code",
    "derivation_description",
    "derivation_source_description",
)


def read_provenance_json(path: Path) -> dict[tuple[str, str], dict[str, str | None]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    foods = payload.get("FoundationFoods")
    if not isinstance(foods, list):
        raise ValueError("Expected FoundationFoods list in USDA JSON.")

    records = {}

    for food in foods:
        fdc_id = food.get("fdcId")
        if fdc_id is None:
            raise ValueError("Foundation food is missing fdcId.")

        for item in food.get("foodNutrients", []):
            nutrient = item.get("nutrient") or {}
            nutrient_id = nutrient.get("id")
            if nutrient_id is None:
                raise ValueError(f"Missing nutrient.id for Foundation food {fdc_id}.")

            key = (str(fdc_id), str(nutrient_id))
            if key in records:
                raise ValueError(f"Duplicate source nutrient pair: {key}")

            derivation = item.get("foodNutrientDerivation") or {}
            derivation_source = derivation.get("foodNutrientSource") or {}

            records[key] = {
                "derivation_code": derivation.get("code"),
                "derivation_description": derivation.get("description"),
                "derivation_source_description": derivation_source.get("description"),
            }

    return records


def import_provenance(
    json_file: Path,
    apply: bool = False,
    expected_matches: int | None = None,
) -> dict[str, int]:
    records = read_provenance_json(json_file)

    records_by_food = defaultdict(dict)
    for (fdc_id, nutrient_id), provenance in records.items():
        records_by_food[fdc_id][nutrient_id] = provenance

    stats = {
        "source_records": len(records),
        "foods_matched": 0,
        "nutrients_matched": 0,
        "nutrients_to_update": 0,
        "nutrients_already_current": 0,
        "foods_not_found": 0,
        "nutrients_not_found": 0,
        "duplicate_database_matches": 0,
        "unknown_derivation_records": 0,
    }

    stats["unknown_derivation_records"] = sum(
        1
        for provenance in records.values()
        if (
            provenance["derivation_code"] not in {"A", "AS", "NC"}
            or not provenance["derivation_description"]
            or not provenance["derivation_source_description"]
        )
    )

    with SessionLocal() as db:
        columns = {
            column["name"]
            for column in inspect(db.get_bind()).get_columns("food_nutrients")
        }
        missing_columns = set(PROVENANCE_FIELDS) - columns
        if missing_columns:
            raise RuntimeError(
                "Migration 0011 is required. Missing columns: "
                + ", ".join(sorted(missing_columns))
            )

        fdc_ids = sorted(records_by_food)

        foods = db.scalars(
            select(Food)
            .options(selectinload(Food.nutrients))
            .where(
                Food.source == SOURCE,
                Food.external_id.in_(fdc_ids),
            )
        ).unique().all()

        foods_by_id = {str(food.external_id): food for food in foods}

        for fdc_id in fdc_ids:
            food = foods_by_id.get(fdc_id)
            if food is None:
                stats["foods_not_found"] += 1
                continue

            stats["foods_matched"] += 1

            nutrients_by_id = defaultdict(list)
            for nutrient in food.nutrients:
                if nutrient.source_nutrient_id is not None:
                    nutrients_by_id[str(nutrient.source_nutrient_id)].append(nutrient)

            for nutrient_id, provenance in records_by_food[fdc_id].items():
                matches = nutrients_by_id.get(nutrient_id, [])

                if len(matches) == 0:
                    stats["nutrients_not_found"] += 1
                    continue

                if len(matches) > 1:
                    stats["duplicate_database_matches"] += 1
                    continue

                nutrient = matches[0]
                stats["nutrients_matched"] += 1


                changed = any(
                    getattr(nutrient, field) != provenance[field]
                    for field in PROVENANCE_FIELDS
                )

                if changed:
                    stats["nutrients_to_update"] += 1
                    if apply:
                        for field in PROVENANCE_FIELDS:
                            setattr(nutrient, field, provenance[field])
                else:
                    stats["nutrients_already_current"] += 1

        if apply:
            if expected_matches is None:
                db.rollback()
                raise RuntimeError(
                    "Refusing to apply without --expected-matches."
                )

            if stats["nutrients_matched"] != expected_matches:
                db.rollback()
                raise RuntimeError(
                    "Match-count safety check failed. "
                    f"Expected {expected_matches}, "
                    f"found {stats['nutrients_matched']}. "
                    "No changes committed."
                )

            if stats["duplicate_database_matches"] > 0:
                db.rollback()
                raise RuntimeError(
                    "Duplicate database matches detected. No changes committed."
                )

            db.commit()
        else:
            db.rollback()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import USDA Foundation nutrient derivation provenance only."
    )
    parser.add_argument("--json-file", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-matches", type=int)
    args = parser.parse_args()

    stats = import_provenance(
        args.json_file,
        apply=args.apply,
        expected_matches=args.expected_matches,
    )

    print("\nUSDA FOUNDATION PROVENANCE IMPORT")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    for key, value in stats.items():
        print(f"{key}: {value}")

    print(
        "\nNo nutrient amounts, units, food records or recipe records were modified."
    )
    print("Database transaction committed." if args.apply else "Dry-run: no changes committed.")


if __name__ == "__main__":
    main()
