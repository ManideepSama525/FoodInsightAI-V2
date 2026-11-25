from types import SimpleNamespace
from backend.app.services.recipe_generation_constraints import build_constraints


def profile(**kw):
    return SimpleNamespace(**kw)


def test_missing_profile_carries_no_private_data():
    assert build_constraints(None) == {"avoid_ingredients": [], "dietary_styles": []}


def test_milk_allergy_maps_aliases_without_severity():
    out = build_constraints(profile(
        allergies=[{"name": "Dairy", "severity": "severe"}, {"name": "groundnuts"}],
        intolerances=[], dietary_preferences=["vegan"], disliked_foods=[],
    ))
    assert out == {"avoid_ingredients": ["milk", "peanut"], "dietary_styles": ["vegan"]}
    assert "severe" not in str(out)


def test_free_text_never_sent_as_personal_data():
    out = build_constraints(profile(
        allergies=[{"name": "Secret doctor note: Call 1234"}, {"name": "milk"}],
        intolerances=[{"name": "Lactose"}],
        dietary_preferences=["jain", "Custom patient preference"],
        disliked_foods=["my private preference", "garlic"],
    ))
    assert out == {"avoid_ingredients": ["garlic", "lactose", "milk"], "dietary_styles": ["jain"]}
    assert "1234" not in str(out)


def test_vegetarian_alias_and_duplicates():
    out = build_constraints(profile(
        allergies=[], intolerances=[], dietary_preferences=["Lacto Vegetarian", "vegetarian"], disliked_foods=[]
    ))
    assert out["dietary_styles"] == ["vegetarian"]
