"""Profile-aware screening for generated recipes; independent of Qwen prompting.

Model output and ingredient lists are unverified. Never declare allergen safety.
"""
import re

from backend.app.schemas.food_profile import FoodSafetyRead
from backend.app.services.food_safety import assess_ingredients, normalize, _term_in_ingredient

_BLOCKING = {"allergy", "intolerance", "dietary_preference"}
_RISK_TERMS = (
    "paneer", "milk", "butter", "ghee", "cream", "cheese", "curd",
    "egg", "chicken", "chicken stock", "meat stock", "fish", "fish sauce",
    "oyster sauce", "shrimp", "prawn", "peanut", "groundnut oil",
    "cashew", "almond", "soy sauce", "tofu", "wheat", "flour",
)
_EXPECTED_TITLE_INGREDIENTS = (
    "paneer", "chicken", "tofu", "egg", "mushroom", "potato", "fish",
    "peanut", "prawn", "lentil",
)
_ASSURANCE = re.compile(
    r"\b(?:100\s*%\s*)?(?:allergen[ -]?free|completely allergy[ -]?safe|"
    r"safe for (?:all|any) allerg(?:y|ies)|guaranteed (?:allergy|allergen)[ -]?safe)\b",
    re.I,
)


def blocked_matches(assessment: FoodSafetyRead) -> list:
    return [m for m in assessment.matches if m.concern_type in _BLOCKING]


def screen_requested_title(title: str, profile) -> FoodSafetyRead:
    # Title-only matches are conservative signals to stop an unsafe request,
    # not proof of actual ingredients or of recipe safety.
    return assess_ingredients([{"name": title}], profile)


def _quality_issues(title: str, ingredients: list[str], steps: list[str], answer: str) -> list[str]:
    issues = []
    keys = []
    for line in ingredients:
        key = normalize(line)
        key = re.sub(
            r"^(?:[\d./ ]+|a |an |one |two )*(?:cups?|tbsps?|tsps?|"
            r"teaspoons?|tablespoons?|grams?|g|kg|ml|l|pieces?|pinch(?:es)?|cloves?)?\s*",
            "", key,
        )
        if key and key in keys:
            issues.append("Repeated ingredient detected: " + line)
        keys.append(key)
    title_norm = normalize(title)
    ingredient_text = " ".join(normalize(x) for x in ingredients)
    for keyword in _EXPECTED_TITLE_INGREDIENTS:
        if _term_in_ingredient(title_norm, keyword) and not _term_in_ingredient(ingredient_text, keyword):
            issues.append("Named main ingredient is absent from the ingredient list: " + keyword)

    steps_norm = " ".join(normalize(x) for x in steps)
    for term in _RISK_TERMS:
        if _term_in_ingredient(steps_norm, term) and not _term_in_ingredient(ingredient_text, term):
            issues.append("Preparation mentions an unlisted ingredient or possible allergen: " + term)
    if _ASSURANCE.search(answer + " " + " ".join(steps)):
        issues.append("Unsupported absolute allergen-safety assurance in model output")
    if any(re.search(r"\b(?:unknown|unidentified|mystery)\b", normalize(x)) for x in ingredients):
        issues.append("Unidentified ingredients require manual verification")
    return list(dict.fromkeys(issues))


def screen_generated_recipe(
    title: str, ingredients: list[str], steps: list[str], answer: str, profile
) -> tuple[FoodSafetyRead, list[str]]:
    listed = assess_ingredients([{"name": i} for i in ingredients], profile)
    issues = _quality_issues(title, ingredients, steps, answer)
    if profile is None:
        return listed, issues
    # Cooking instructions can reveal undeclared ingredients, so screen
    # them independently. Never trust only the model's ingredient list.
    step_scan = assess_ingredients([{"name": x} for x in steps], profile)
    seen = {(m.ingredient, m.concern, m.concern_type) for m in listed.matches}
    for match in step_scan.matches:
        key = (match.ingredient, match.concern, match.concern_type)
        if key not in seen:
            seen.add(key)
            listed.matches.append(match.model_copy(update={
                "message": "Preparation instruction: " + match.message,
            }))
    if any(m.concern_type == "allergy" for m in listed.matches):
        listed.status = "allergy_conflict"
    elif listed.matches:
        listed.status = "preference_conflict"
    else:
        listed.status = "insufficient_evidence"
    return listed, issues
