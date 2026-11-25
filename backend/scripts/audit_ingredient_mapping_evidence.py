import csv
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models.food import Food
from backend.app.models.recipe import IngredientAlias
from backend.scripts.import_recipe_datasets import (
    adapt_indian,
    normalize_ingredient_alias,
    is_compound_ingredient_for_review,
)

SOURCE = "/tmp/IndianFoodDatasetCSV.csv"
OUTPUT = "/tmp/ingredient_mapping_evidence_audit.csv"

db = SessionLocal()
try:
    aliases = db.scalars(select(IngredientAlias).where(
        IngredientAlias.status == "approved",
        IngredientAlias.food_id.is_not(None),
    )).all()

    approved = {}
    for alias in aliases:
        food = db.get(Food, alias.food_id)
        if food:
            approved[alias.normalized_alias] = food

    counts = Counter()
    examples = {}

    with open(SOURCE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            record = adapt_indian(row)
            for raw in record.get("ingredients", []):
                key = normalize_ingredient_alias(raw)
                if not key or is_compound_ingredient_for_review(raw):
                    continue
                food = approved.get(key)
                if food is None:
                    continue

                raw = raw.strip()
                counts[(key, raw, food.id, food.name)] += 1

    rows = []
    for (key, raw, food_id, food_name), count in sorted(
        counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
    ):
        flags = []
        low = raw.casefold()

        if key == "garlic" and re.search(
            r"\b(paste|powder|dried|roasted|granules?)\b", low
        ):
            flags.append("GARLIC_FORM_REVIEW")

        if key == "sunflower oil" and re.search(
            r"\b(blend|mixed|flavoured|infused)\b", low
        ):
            flags.append("OIL_FORM_REVIEW")

        rows.append({
            "normalized_alias": key,
            "raw_ingredient_text": raw,
            "occurrences": count,
            "food_id": food_id,
            "food_name": food_name,
            "review_flags": ";".join(flags),
        })

    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "normalized_alias", "raw_ingredient_text", "occurrences",
            "food_id", "food_name", "review_flags"
        ])
        writer.writeheader()
        writer.writerows(rows)

    print({
        "mapped_occurrences": sum(counts.values()),
        "distinct_raw_forms": len(rows),
        "approved_aliases_used": len(set(k[0] for k in counts)),
        "flagged_forms": sum(bool(r["review_flags"]) for r in rows),
        "report": OUTPUT,
    })
finally:
    db.close()
