"""Parsing and structural validation of generated recipe text.

The structural checks mirror ``training/evaluate.py`` (``recipe_format`` and
``ingredient_coverage``) so that the same numbers reported in
``evaluation/comparison.md`` can be reproduced against live output.

IMPORTANT: these helpers only measure *structure* (does the answer have an
ingredients block and >= 2 numbered steps) and *lexical ingredient coverage*.
They do NOT validate nutrition, allergen or food-safety correctness, and the
service must not claim those are verified.
"""

from __future__ import annotations

import re
from typing import Iterable

_INGREDIENTS_HEADER = re.compile(r"ingredients?\s*:", re.I)
_STEPS_HEADER = re.compile(r"(instructions?|directions?|method|steps)\s*:", re.I)
_NUMBERED_STEP = re.compile(r"(?m)^\s*\d+[\.\)]\s+")
_BULLET_ITEM = re.compile(r"(?m)^\s*[-*\u2022]\s+(.+)$")


def split_sections(text: str) -> dict:
    """Split a generated answer into an ingredients list and step list.

    Tolerant of the ways a 4B model may format output. Returns
    ``{"ingredients": [...], "steps": [...], "has_ingredients_section": bool,
    "has_steps_section": bool, "numbered_steps": int}``.
    """
    text = text or ""
    numbered = _NUMBERED_STEP.findall(text)
    bullets = [m.group(1).strip() for m in _BULLET_ITEM.finditer(text)]

    # Take everything after an explicit "Ingredients:" header, up to a steps
    # header, as the ingredient block.
    ingredients: list[str] = []
    steps: list[str] = []

    lower = text
    ing_match = _INGREDIENTS_HEADER.search(lower)
    step_match = _STEPS_HEADER.search(lower)

    if ing_match:
        start = ing_match.end()
        end = step_match.start() if step_match and step_match.start() > start else len(text)
        block = text[start:end]
        ingredients = [m.group(1).strip() for m in _BULLET_ITEM.finditer(block)]
        if not ingredients:
            ingredients = [ln.strip(" -*\t") for ln in block.splitlines() if ln.strip()]

    if step_match:
        block = text[step_match.end():]
        steps = [m.group(0).strip() for m in re.finditer(r"(?m)^\s*\d+[\.\)]\s+.+$", block)]
        if not steps:
            steps = [ln.strip() for ln in block.splitlines() if ln.strip()]

    return {
        "ingredients": ingredients,
        "steps": steps,
        "bullets": bullets,
        "has_ingredients_section": bool(ing_match),
        "has_steps_section": bool(step_match) or len(numbered) >= 2,
        "numbered_steps": len(numbered),
    }


def recipe_format(text: str) -> dict:
    """Structural compliance report (same definition as evaluate.py)."""
    has_ingredients = bool(_INGREDIENTS_HEADER.search(text or ""))
    numbered = _NUMBERED_STEP.findall(text or "")
    has_steps_header = bool(_STEPS_HEADER.search(text or ""))
    return {
        "has_ingredients_section": has_ingredients,
        "has_steps_section": has_steps_header or len(numbered) >= 2,
        "numbered_steps": len(numbered),
        "format_ok": has_ingredients
        and (has_steps_header or len(numbered) >= 2)
        and len(numbered) >= 2,
    }


def ingredient_coverage(text: str, terms: Iterable[str]) -> float:
    """Fraction of expected ingredient terms that appear in the answer."""
    terms = [t for t in terms if t]
    if not terms:
        return 1.0
    lowered = (text or "").lower()
    hits = sum(1 for term in terms if str(term).lower() in lowered)
    return hits / len(terms)


def strip_role_prefixes(text: str) -> str:
    """Remove stray ``assistant`` / ``Ingredients`` role leakage if present."""
    text = text or ""
    text = re.sub(r"^\s*(assistant|system|user)\s*:?\s*", "", text, flags=re.I)
    return text.strip()
