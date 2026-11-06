from types import SimpleNamespace

import pytest

from backend.app.services.food_safety import (
    assess_ingredients,
    ingredient_matches_concern,
)


def make_profile(**overrides):
    values = {
        "allergies": [],
        "intolerances": [],
        "dietary_preferences": [],
        "goals": [],
        "disliked_foods": [],
        "cuisine_interests": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_groundnut_alias_matches_peanut_allergy():
    profile = make_profile(
        allergies=[{"name": "peanut", "severity": "severe"}]
    )
    result = assess_ingredients(
        [{"name": "groundnut oil", "confidence": 0.99}], profile
    )
    assert result.status == "allergy_conflict"
    assert result.matches[0].concern_type == "allergy"
    assert result.safe_to_assume is False


def test_compound_ingredient_matches_allergen_phrase():
    assert ingredient_matches_concern("peanut butter", "peanut")
    assert ingredient_matches_concern("almond flour", "tree nuts")
    assert ingredient_matches_concern("wheat semolina", "wheat")


def test_low_confidence_allergen_is_possible_and_unknown():
    profile = make_profile(
        allergies=[{"name": "peanut", "severity": "severe"}]
    )
    result = assess_ingredients(
        [{"name": "peanut", "confidence": 0.4}], profile
    )
    assert result.status == "allergy_conflict"
    assert result.matches[0].certainty == "possible"
    assert result.unknown_ingredients == ["peanut"]


def test_missing_confidence_is_not_treated_as_confirmed():
    profile = make_profile(
        allergies=[{"name": "peanut", "severity": "severe"}]
    )
    result = assess_ingredients([{"name": "peanut"}], profile)
    assert result.matches[0].certainty == "possible"
    assert result.unknown_ingredients == ["peanut"]


def test_unknown_ingredients_prevent_no_conflict_status():
    result = assess_ingredients(
        [{"name": "unidentified sauce", "confidence": None}],
        make_profile(),
    )
    assert result.status == "insufficient_evidence"
    assert result.safe_to_assume is False


def test_missing_profile_never_assumes_safety():
    result = assess_ingredients(
        [{"name": "rice", "confidence": 0.99}], None
    )
    assert result.status == "profile_missing"
    assert result.safe_to_assume is False
    assert result.unknown_ingredients == ["rice"]


@pytest.mark.parametrize(
    ("preference", "ingredient"),
    [
        ("vegan", "milk"),
        ("vegan", "honey"),
        ("vegetarian", "gelatin"),
        ("eggetarian", "chicken"),
        ("jain", "onion"),
        ("jain", "egg"),
    ],
)
def test_dietary_conflicts(preference, ingredient):
    result = assess_ingredients(
        [{"name": ingredient, "confidence": 0.99}],
        make_profile(dietary_preferences=[preference]),
    )
    assert result.status == "preference_conflict"
    assert any(
        match.concern_type == "dietary_preference"
        for match in result.matches
    )


def test_vegetarian_profile_does_not_reject_egg_by_default():
    result = assess_ingredients(
        [{"name": "egg", "confidence": 0.99}],
        make_profile(dietary_preferences=["vegetarian"]),
    )
    assert result.status == "no_known_conflict"


def test_disliked_compound_ingredient_is_detected():
    result = assess_ingredients(
        [{"name": "peanut butter", "confidence": 0.99}],
        make_profile(disliked_foods=["peanut"]),
    )
    assert result.status == "preference_conflict"
    assert result.matches[0].concern_type == "disliked_food"


def test_known_non_conflicting_ingredient_has_no_unknowns():
    result = assess_ingredients(
        [{"name": "rice", "confidence": 0.99}],
        make_profile(),
    )
    assert result.status == "no_known_conflict"
    assert result.unknown_ingredients == []
    assert result.safe_to_assume is False