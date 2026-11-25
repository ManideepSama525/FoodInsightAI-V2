"""Deterministic recipe-safety regression tests (no Qwen, GPU, or network)."""
from types import SimpleNamespace

import pytest

from backend.app.services.food_safety import assess_ingredients, ingredient_matches_concern
from backend.app.services.generated_recipe_safety import (
    blocked_matches, screen_generated_recipe, screen_requested_title,
)


def profile(*, allergies=(), intolerances=(), preferences=()):
    return SimpleNamespace(
        allergies=[{"name": name, "severity": "severe"} for name in allergies],
        intolerances=[{"name": name, "severity": "unspecified"} for name in intolerances],
        dietary_preferences=list(preferences), disliked_foods=[],
    )


@pytest.mark.parametrize("item, allergy", [
    ("Paneer curry", "milk"),
    ("250 g cottage cheese", "milk"),
    ("Groundnut oil", "peanut"),
    ("Almond flour", "tree nuts"),
    ("Tofu", "soy"),
    ("Prawn curry", "crustacean shellfish"),
    ("Egg whites", "egg"),
    ("Salmon fillet", "fish"),
    ("Dahi", "milk"),
    ("Scallops", "molluscan shellfish"),
    ("Edamame beans", "soy"),
])
def test_known_allergen_families(item, allergy):
    result = assess_ingredients([{"name": item}], profile(allergies=[allergy]))
    assert result.status == "allergy_conflict"
    assert blocked_matches(result)
    assert result.safe_to_assume is False


@pytest.mark.parametrize("title, preference", [
    ("Paneer curry", "vegan"),
    ("Chicken stock soup", "vegetarian"),
    ("Egg curry", "vegan"),
    ("Onion garlic curry", "jain"),
    ("Carrots and onions curry", "jain"),
])
def test_preflight_preferences_block(title, preference):
    result = screen_requested_title(title, profile(preferences=[preference]))
    assert blocked_matches(result)


def test_milk_allergy_preflight_blocks_paneer():
    result = screen_requested_title("Paneer curry", profile(allergies=["milk"]))
    assert result.status == "allergy_conflict"
    assert any(m.concern_type == "allergy" for m in blocked_matches(result))
    assert any("Paneer is made from milk" in m.message for m in result.matches)


def test_conflicting_step_blocked_even_if_ingredient_list_looks_safe():
    result, issues = screen_generated_recipe(
        "Vegetable soup", ["carrots", "water"],
        ["Boil the carrots.", "Stir in chicken stock and cook."],
        "A quick vegetable soup", profile(preferences=["vegetarian"]),
    )
    assert blocked_matches(result)
    assert any("chicken" in issue.lower() for issue in issues)


def test_groundnut_oil_in_steps_flags_peanut_allergy():
    result, _ = screen_generated_recipe(
        "Cucumber salad", ["cucumber", "salt"],
        ["Chop cucumber", "Drizzle groundnut oil over salad."],
        "Cucumber salad", profile(allergies=["peanut"]),
    )
    assert result.status == "allergy_conflict"


def test_missing_profile_is_unknown_not_safe():
    assessment, _ = screen_generated_recipe(
        "Rice", ["rice", "water"], ["Boil rice in water"], "Rice recipe", None,
    )
    assert assessment.status == "profile_missing"
    assert assessment.safe_to_assume is False


def test_ambiguous_sauce_requires_review():
    result, issues = screen_generated_recipe(
        "Rice", ["rice", "unidentified sauce"], ["Cook rice"],
        "Recipe", profile(allergies=["peanut"]),
    )
    assert result.safe_to_assume is False
    assert any("Unidentified" in issue for issue in issues)


def test_repeat_ingredients_and_missing_named_main_ingredient():
    result, issues = screen_generated_recipe(
        "Paneer curry", ["2 cups tomato", "3 cups tomato"],
        ["Cook tomato"], "Recipe", profile(),
    )
    assert any("Repeated ingredient" in issue for issue in issues)
    assert any("Named main ingredient" in issue for issue in issues)


def test_absolute_safety_claim_is_rejected_as_quality_issue():
    _, issues = screen_generated_recipe(
        "Rice", ["rice", "water"], ["Boil"],
        "This recipe is guaranteed allergen-free.", profile(),
    )
    assert any("Unsupported absolute" in issue for issue in issues)


def test_plant_milk_not_identical_to_cow_milk():
    assert not ingredient_matches_concern("1 cup coconut milk", "milk")
    assert not ingredient_matches_concern("1 tbsp almond milk", "milk")
    assert ingredient_matches_concern("almond milk with dahi", "milk")
    assert not ingredient_matches_concern("almond milk and peanut butter", "milk")
    assert ingredient_matches_concern("almond milk", "tree nuts")
    assert not assess_ingredients([{"name": "coconut milk"}], profile(preferences=["vegan"])).matches


def test_nut_butter_is_not_automatically_dairy():
    assert not ingredient_matches_concern("peanut butter", "milk")
    assert not assess_ingredients([{"name": "peanut butter"}], profile(preferences=["vegan"])).matches


def test_wheat_allergy_distinct_from_gluten_sensitivity():
    assert not ingredient_matches_concern("barley flour", "wheat")
    assert ingredient_matches_concern("barley flour", "gluten")
    assert ingredient_matches_concern("wheat atta", "wheat")
