"""Prompt templates for recipe generation.

These strings are copied *verbatim* from the training data builder
(``training/prepare.py``, already delivered in ``recsi.zip``) so that the
inference prompts are byte-identical to the prompts the adapter was
supervised on. Changing them will degrade output; keep them in sync with
``prepare.py`` if that file ever changes.
"""

from __future__ import annotations

# training/prepare.py :: SYSTEM  (verbatim)
SYSTEM_PROMPT = (
    "You are FoodInsightAI, an evidence-grounded food science assistant. "
    "Answer using the reference data provided. Never invent allergens, "
    "nutrition values, sources, or food-safety facts. If the reference data "
    "does not support an answer, say so. Answer directly and concisely."
)

# training/prepare.py :: recipe_example()  (verbatim wording)
RECIPE_USER_TEMPLATE = (
    'Write a recipe for "{title}". Provide an ingredient list '
    "and numbered preparation steps."
)

# The adapter was also trained on the allergen tasks (listing + containment).
# They are provided here for completeness/testing only; the integration brief
# asks for recipe generation, so the service exposes that task by default.
ALLERGEN_LISTING_USER_TEMPLATE = (
    'List the regulated (EU-14) allergens associated with the food "{food}". '
    "If none are recorded, say so."
)

ALLERGEN_CONTAINMENT_USER_TEMPLATE = (
    'Does the food "{food}" contain the allergen {allergen}?'
)


def recipe_messages(title: str) -> list[dict]:
    """Return the chat messages for a recipe-generation request."""
    title = (title or "").strip()
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": RECIPE_USER_TEMPLATE.format(title=title)},
    ]


def allergen_listing_messages(food: str) -> list[dict]:
    food = (food or "").strip()
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": ALLERGEN_LISTING_USER_TEMPLATE.format(food=food)},
    ]


def allergen_containment_messages(food: str, allergen: str) -> list[dict]:
    food = (food or "").strip()
    allergen = (allergen or "").strip()
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": ALLERGEN_CONTAINMENT_USER_TEMPLATE.format(
                food=food, allergen=allergen
            ),
        },
    ]
