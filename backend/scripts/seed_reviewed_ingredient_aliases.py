"""Seed reviewed Indian recipe ingredient aliases.

Dry-run is the default. Pass --apply to insert missing aliases.
Existing aliases are never overwritten. Conflicts abort before any writes.
"""
from __future__ import annotations

import argparse
from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models.food import Food
from backend.app.models.recipe import IngredientAlias
from backend.scripts.import_recipe_datasets import normalize_ingredient_alias

SOURCE = "indian_recipe_review"

# Status "approved" is reserved for unambiguous identity matches.
# All other rows are candidate suggestions and cannot feed nutrition calculations.
CATALOGUE = [
    ("Sunflower Oil", 126, "approved", "USDA record explicitly identifies sunflower oil."),
    ("Garlic", 111, "approved", "Plain fresh garlic corresponds to raw garlic; excludes powders and prepared pastes."),
    ("Extra Virgin Olive Oil", 97, "approved", "Exact oil subtype and descriptor match the verified USDA record."),
    ("Salt", 60, "review_required", "USDA candidate is iodized table salt; recipe source does not specify salt type."),
    ("Onion", 109, "review_required", "Candidate is red onion; recipe source does not specify onion variety."),
    ("Onions", 109, "review_required", "Candidate is red onion; recipe source does not specify onion variety."),
    ("Tomato", 137, "review_required", "Candidate is raw Roma tomato; source does not specify variety or preparation."),
    ("Tomatoes", 137, "review_required", "Candidate is raw Roma tomato; source does not specify variety or preparation."),
    ("Milk", 67, "review_required", "Candidate is whole milk; source does not specify fat percentage."),
    ("Curd (Dahi / Yogurt)", 167, "review_required", "Candidate is plain whole-milk yogurt; source does not specify style or fat level."),
    ("Butter", 100, "review_required", "Candidate is unsalted butter; source does not specify salted or unsalted."),
    ("Whole Wheat Flour", 104, "review_required", "Candidate is unenriched whole-wheat flour; enrichment is unspecified."),
    ("Sugar", 69, "review_required", "Candidate is granulated sugar; source does not specify sugar form."),
    ("Cashew nuts", 226, "review_required", "Candidate is raw cashew; source does not specify raw or roasted."),
    ("Green Bell Pepper (Capsicum)", 162, "review_required", "Candidate is raw green bell pepper; preparation is not specified."),
    ("Carrot (Gajjar)", 160, "review_required", "Candidate is mature raw carrot; source may use another form or preparation."),
    ("Whole Eggs", 98, "review_required", "Candidate is Grade A large whole egg; source does not specify egg size."),
    ("Fresh cream", 180, "review_required", "Candidate is heavy cream; source does not specify fat content."),
    ("Coconut Oil", 29, "review_required", "Candidate is coconut oil; source does not specify refinement or product form."),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Insert missing aliases. Default is dry-run.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Verify all candidate IDs and exact expected names before preparing records.
        ids = sorted({food_id for _, food_id, _, _ in CATALOGUE})
        foods = {
            food.id: food
            for food in db.scalars(select(Food).where(Food.id.in_(ids))).all()
        }
        if set(foods) != set(ids):
            missing = sorted(set(ids) - set(foods))
            raise RuntimeError(f"Missing canonical Food IDs: {missing}")

        expected_names = {
            29: "Oil, coconut",
            60: "Salt, table, iodized",
            67: "Milk, whole, 3.25% milkfat, with added vitamin D",
            69: "Sugars, granulated",
            97: "Oil, olive, extra virgin",
            98: "Eggs, Grade A, Large, egg whole",
            100: "Butter, stick, unsalted",
            104: "Flour, whole wheat, unenriched",
            109: "Onions, red, raw",
            111: "Garlic, raw",
            126: "Oil, sunflower",
            137: "Tomato, roma",
            160: "Carrots, mature, raw",
            162: "Peppers, bell, green, raw",
            167: "Yogurt, plain, whole milk",
            180: "Cream, heavy",
            226: "Nuts, cashew nuts, raw",
        }
        for food_id, expected in expected_names.items():
            actual = foods[food_id].name
            if actual != expected:
                raise RuntimeError(
                    f"Food ID verification failed: {food_id}: expected {expected!r}, got {actual!r}"
                )

        # Consolidate by the exact normalizer used by the recipe importer.
        desired = {}
        for alias, food_id, status, reason in CATALOGUE:
            normalized = normalize_ingredient_alias(alias)
            if not normalized:
                raise RuntimeError(f"Empty normalized alias: {alias!r}")
            row = {
                "alias": alias,
                "normalized_alias": normalized,
                "food_id": food_id if status == "approved" else None,
                "candidate_food_id": None if status == "approved" else food_id,
                "status": status,
                "source": SOURCE,
                "provenance": {
                    "dataset": "IndianFoodDatasetCSV.csv",
                    "review_basis": "USDA Food ID and name verified against active database",
                    "review_reason": reason,
                    "nutrition_mapping": status == "approved",
                },
            }
            prior = desired.get(normalized)
            if prior and prior != row:
                raise RuntimeError(f"Catalogue normalization collision: {normalized!r}")
            desired[normalized] = row

        existing = {
            item.normalized_alias: item
            for item in db.scalars(
                select(IngredientAlias).where(
                    IngredientAlias.normalized_alias.in_(list(desired))
                )
            ).all()
        }

        inserted = []
        unchanged = []
        conflicts = []
        for normalized, values in desired.items():
            current = existing.get(normalized)
            if current is None:
                inserted.append(values)
                continue
            same = (
                current.alias == values["alias"]
                and current.food_id == values["food_id"]
                and current.candidate_food_id == values["candidate_food_id"]
                and current.status == values["status"]
            )
            if same:
                unchanged.append(normalized)
            else:
                conflicts.append({
                    "normalized_alias": normalized,
                    "existing": {
                        "alias": current.alias,
                        "food_id": current.food_id,
                        "candidate_food_id": current.candidate_food_id,
                        "status": current.status,
                        "source": current.source,
                    },
                    "requested": values,
                })

        report = {
            "mode": "apply" if args.apply else "dry_run",
            "catalogue_rows": len(CATALOGUE),
            "unique_normalized_aliases": len(desired),
            "approved_new": sum(x["status"] == "approved" for x in inserted),
            "review_required_new": sum(x["status"] == "review_required" for x in inserted),
            "already_present_unchanged": len(unchanged),
            "conflicts": conflicts,
            "inserted": 0,
        }
        if conflicts:
            db.rollback()
            print(report)
            raise RuntimeError("Alias conflicts found; no rows were written.")

        if args.apply:
            for values in inserted:
                db.add(IngredientAlias(**values))
            db.commit()
            report["inserted"] = len(inserted)
        else:
            db.rollback()

        print(report)
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
