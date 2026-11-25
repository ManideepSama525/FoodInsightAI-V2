"""Read-only ingredient coverage audit with conservative canonical candidates."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models.food import Food
from backend.app.models.recipe import IngredientAlias
from backend.scripts.import_recipe_datasets import (
    adapt_indian,
    adapt_international,
    normalize,
    normalize_ingredient_alias,
    normalize_ingredient_display,
)


def canonical_candidates(display: str, foods: list[Food]) -> list[dict]:
    """Return conservative token-subset candidates; never approve or map them."""
    query_tokens = set(normalize(display).split())
    if not query_tokens:
        return []

    candidates = []
    for food in foods:
        name_tokens = set(normalize(food.name).split())
        if not query_tokens.issubset(name_tokens):
            continue

        extra_tokens = name_tokens - query_tokens
        # Prevent broad terms such as "sugar" or "oil" matching long composite foods.
        if len(extra_tokens) > 2:
            continue

        candidates.append({
            "food_id": food.id,
            "canonical_food": food.name,
            "extra_tokens": sorted(extra_tokens),
            "extra_token_count": len(extra_tokens),
        })

    candidates.sort(key=lambda item: (item["extra_token_count"], item["canonical_food"]))
    return candidates[:10]


def audit(db, records):
    foods = db.scalars(select(Food).order_by(Food.id)).all()
    direct = {normalize(food.name): food for food in foods if normalize(food.name)}
    aliases = db.scalars(select(IngredientAlias).where(
        IngredientAlias.status == "approved",
        IngredientAlias.food_id.is_not(None),
    )).all()

    approved = {}
    for alias in aliases:
        food = db.get(Food, alias.food_id)
        if food is not None:
            approved[alias.normalized_alias] = food

    counts = Counter()
    exact_usage = Counter()
    alias_usage = Counter()
    candidate_usage = Counter()
    ambiguous_usage = Counter()
    missing_usage = Counter()
    empty_usage = Counter()
    examples = {}

    for record in records:
        for raw in record.get("ingredients") or []:
            raw = (raw or "").strip()
            key = normalize_ingredient_alias(raw)
            if not key:
                counts["empty_or_unparseable_entries"] += 1
                empty_usage[raw or "<empty>"] += 1
                continue

            counts["ingredient_entries"] += 1
            if key in approved:
                food = approved[key]
                counts["approved_alias_mapped"] += 1
                alias_usage[(key, food.id, food.name)] += 1
                continue

            display = normalize_ingredient_display(raw)
            display_key = normalize(display)
            exact_food = direct.get(display_key)
            if exact_food is not None:
                counts["exact_canonical_mapped"] += 1
                exact_usage[(display_key, exact_food.id, exact_food.name)] += 1
                continue

            candidates = canonical_candidates(key, foods)
            if len(candidates) == 1:
                counts["single_candidate_review"] += 1
                candidate_usage[(key, candidates[0]["food_id"], candidates[0]["canonical_food"])] += 1
                examples.setdefault(key, {
                    "display": display,
                    "raw_example": raw,
                    "candidates": candidates,
                })
            elif len(candidates) > 1:
                counts["ambiguous_candidate_review"] += 1
                ambiguous_usage[key] += 1
                examples.setdefault(key, {
                    "display": display,
                    "raw_example": raw,
                    "candidates": candidates,
                })
            else:
                counts["no_candidate_found"] += 1
                missing_usage[key] += 1
                examples.setdefault(key, {
                    "display": display,
                    "raw_example": raw,
                    "candidates": [],
                })

    def usage_rows(counter, fields):
        rows = []
        for key, count in counter.most_common(200):
            values = list(key) if isinstance(key, tuple) else [key]
            rows.append({**dict(zip(fields, values)), "occurrences": count})
        return rows

    return {
        "canonical_food_count": len(foods),
        "approved_alias_count": len(approved),
        **dict(counts),
        "mapping_policy": (
            "Only approved aliases and exact canonical-name matches are mapped. "
            "Candidate matches are review suggestions and are never used for nutrition."
        ),
        "top_exact_canonical_usage": usage_rows(
            exact_usage, ["normalized_ingredient", "food_id", "canonical_food"]
        ),
        "top_approved_alias_usage": usage_rows(
            alias_usage, ["normalized_ingredient", "food_id", "canonical_food"]
        ),
        "top_single_candidate_review": usage_rows(
            candidate_usage, ["normalized_ingredient", "candidate_food_id", "candidate_food"]
        ),
        "top_ambiguous_review": usage_rows(ambiguous_usage, ["normalized_ingredient"]),
        "top_no_candidate": usage_rows(missing_usage, ["normalized_ingredient"]),
        "top_empty_or_unparseable": usage_rows(empty_usage, ["raw_ingredient"]),
        "ingredient_review_examples": [
            {"normalized_ingredient": key, **value}
            for key, value in list(examples.items())[:500]
        ],
    }


def rows_from_csv(path: Path, adapter):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            yield adapter(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--indian-csv", type=Path)
    parser.add_argument("--international-csv", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.indian_csv and not args.international_csv:
        parser.error("Provide at least one dataset CSV.")

    def records():
        if args.indian_csv:
            yield from rows_from_csv(args.indian_csv, adapt_indian)
        if args.international_csv:
            yield from rows_from_csv(args.international_csv, adapt_international)

    db = SessionLocal()
    try:
        result = audit(db, records())
    finally:
        db.close()

    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Report written: {args.output}")
    print(json.dumps({k: v for k, v in result.items() if not k.startswith("top_") and k != "ingredient_review_examples"}, indent=2))


if __name__ == "__main__":
    main()
