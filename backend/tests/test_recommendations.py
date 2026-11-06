from types import SimpleNamespace

from backend.app.services.recommendations import recommend_foods


def make_food(food_id, name, nutrients):
    records = [
        SimpleNamespace(
            nutrient_key=key,
            display_name=key.replace("_", " ").title(),
            amount=amount,
            unit="g" if key != "energy_kcal" else "kcal",
            basis_g=basis,
            source="test",
        )
        for key, amount, basis in nutrients
    ]
    return SimpleNamespace(
        id=food_id,
        name=name,
        category="test",
        source="test",
        nutrients=records,
    )


def make_profile(**overrides):
    values = {
        "goals": [],
        "allergies": [],
        "intolerances": [],
        "dietary_preferences": [],
        "disliked_foods": [],
        "cuisine_interests": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_high_protein_ranks_foods_by_protein_per_100g():
    foods = [
        make_food(1, "Food A", [("protein", 5, 100)]),
        make_food(2, "Food B", [("protein", 20, 100)]),
    ]
    result = recommend_foods(foods, make_profile(goals=["high protein"]))

    assert result["goals_used"] == ["high protein"]
    assert [item["food_id"] for item in result["recommendations"]] == [2, 1]
    assert result["recommendations"][0]["score"] == 100.0
    assert result["recommendations"][1]["score"] == 0.0


def test_nutrient_basis_is_normalized_to_100g():
    foods = [
        make_food(1, "Food A", [("protein", 10, 50)]),
        make_food(2, "Food B", [("protein", 15, 100)]),
    ]
    result = recommend_foods(foods, make_profile(goals=["high protein"]))

    assert result["recommendations"][0]["food_id"] == 1
    assert result["recommendations"][0]["nutrients_per_100g"][0][
        "amount_per_100g"
    ] == 20.0


def test_single_comparable_food_is_not_given_an_automatic_top_score():
    foods = [make_food(1, "Only Food", [("protein", 10, 100)])]
    result = recommend_foods(foods, make_profile(goals=["high protein"]))

    assert result["recommendations"] == []


def test_missing_nutrients_are_not_treated_as_zero():
    foods = [
        make_food(1, "Food A", [("protein", None, 100)]),
        make_food(2, "Food B", [("fiber", 4, 100)]),
    ]
    result = recommend_foods(foods, make_profile(goals=["high protein"]))

    assert result["recommendations"] == []


def test_unknown_goal_falls_back_to_balanced_nutrition():
    foods = [
        make_food(1, "Food A", [("protein", 5, 100)]),
        make_food(2, "Food B", [("protein", 15, 100)]),
    ]
    result = recommend_foods(foods, make_profile(goals=["unknown goal"]))

    assert result["goals_used"] == ["balanced nutrition"]
    assert [item["food_id"] for item in result["recommendations"]] == [2, 1]


def test_muscle_building_uses_protein_not_energy_as_a_target():
    foods = [
        make_food(1, "Food A", [("protein", 5, 100), ("energy_kcal", 400, 100)]),
        make_food(2, "Food B", [("protein", 20, 100), ("energy_kcal", 100, 100)]),
    ]
    result = recommend_foods(foods, make_profile(goals=["muscle building"]))

    assert result["recommendations"][0]["food_id"] == 2
    assert "energy_kcal" not in result["recommendations"][0]["reasons"][0]


def test_allergen_name_match_is_excluded_and_not_claimed_as_confirmed():
    foods = [
        make_food(1, "Peanut butter", [("protein", 20, 100)]),
        make_food(2, "Rice", [("protein", 2, 100)]),
        make_food(3, "Lentils", [("protein", 9, 100)]),
    ]
    profile = make_profile(
        goals=["high protein"],
        allergies=[{"name": "peanut", "severity": "severe"}],
    )
    result = recommend_foods(foods, profile)

    assert result["excluded_known_conflicts"] == 1
    assert all(item["food_id"] != 1 for item in result["recommendations"])
    assert all(
        "possible-match confidence" in item["safety_note"]
        for item in result["recommendations"]
    )


def test_limit_is_enforced():
    foods = [
        make_food(index, f"Food {index}", [("protein", index, 100)])
        for index in range(1, 6)
    ]
    result = recommend_foods(
        foods,
        make_profile(goals=["high protein"]),
        limit=2,
    )

    assert len(result["recommendations"]) == 2