"""Exact, curated recognition-label resolution to canonical Food records."""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.food import Food, RecognitionAlias


def normalize_recognition_label(label: str) -> str:
    """Normalize casing, Unicode, and whitespace without fuzzy substitutions."""
    normalized = unicodedata.normalize("NFKC", label).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def resolve_recognition_alias(
    db: Session, label: str, model_source: str
) -> Food | None:
    """Resolve only an active exact alias; model-specific aliases take precedence."""
    normalized = normalize_recognition_label(label)
    if not normalized:
        return None

    rows = db.execute(
        select(RecognitionAlias, Food)
        .join(Food, Food.id == RecognitionAlias.food_id)
        .where(
            RecognitionAlias.normalized_label == normalized,
            RecognitionAlias.is_active.is_(True),
            RecognitionAlias.model_source.in_([model_source, "any"]),
        )
        .order_by((RecognitionAlias.model_source == model_source).desc())
    ).all()

    if not rows:
        return None
    # Ambiguous fallback aliases are rejected rather than guessed.
    best_specificity = rows[0][0].model_source == model_source
    matches = [
        food for alias, food in rows
        if (alias.model_source == model_source) == best_specificity
    ]
    unique_foods = {food.id: food for food in matches}
    return next(iter(unique_foods.values())) if len(unique_foods) == 1 else None
