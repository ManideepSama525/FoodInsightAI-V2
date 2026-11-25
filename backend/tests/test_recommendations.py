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

def test_negative_nutrient_is_not_used_for_recommendation_ranking():
    foods = [
        make_food(1, "Negative protein", [("protein", -5, 100)]),
        make_food(2, "Valid protein A", [("protein", 10, 100)]),
        make_food(3, "Valid protein B", [("protein", 5, 100)]),
    ]
    result = recommend_foods(foods, make_profile(goals=["high protein"]))
    assert [item["food_id"] for item in result["recommendations"]] == [2, 3]


def test_recommendation_reports_nutrient_coverage_and_missing_values():
    foods = [
        make_food(
            1,
            "Food A",
            [
                ("protein", 10, 100),
                ("fiber", None, 100),
                ("sodium", -5, 100),
            ],
        ),
        make_food(
            2,
            "Food B",
            [
                ("protein", 20, 100),
                ("fiber", 4, 100),
                ("sodium", 0, 100),
            ],
        ),
    ]

    result = recommend_foods(
        foods,
        make_profile(goals=["high protein"]),
    )

    quality = result["nutrient_data_quality"]

    assert quality["total_records"] == 6
    assert quality["available"] == 4
    assert quality["missing"] == 1
    assert quality["invalid"] == 1
    assert quality["coverage_percent"] == 66.67
    assert quality["invalid_reasons"] == {"negative_amount": 1}


def test_recommendation_exposes_per_food_quality():
    foods = [
        make_food(
            1,
            "Food A",
            [
                ("protein", 10, 100),
                ("fiber", None, 100),
            ],
        ),
        make_food(
            2,
            "Food B",
            [
                ("protein", 20, 100),
                ("fiber", 4, 100),
            ],
        ),
    ]

    result = recommend_foods(
        foods,
        make_profile(goals=["high protein"]),
    )

    first = next(
        item for item in result["recommendations"]
        if item["food_id"] == 1
    )

    quality = first["nutrient_data_quality"]

    assert quality["total_records"] == 2
    assert quality["available"] == 1
    assert quality["missing"] == 1
    assert quality["coverage_percent"] == 50.0

    fiber = next(
        item for item in first["nutrients_per_100g"]
        if item["key"] == "fiber"
    )

    assert fiber["amount_per_100g"] is None
    assert fiber["data_status"] == "missing"
    assert fiber["data_quality_reason"] == "missing"


def test_empty_catalog_has_undefined_coverage():
    result = recommend_foods(
        [],
        make_profile(goals=["high protein"]),
    )

    assert result["nutrient_data_quality"]["total_records"] == 0
    assert result["nutrient_data_quality"]["coverage_percent"] is None
    assert result["recommendations"] == []


def test_recommendation_reports_per_nutrient_coverage():
    foods = [
        make_food(
            1,
            "Food A",
            [
                ("protein", 10, 100),
                ("fiber", None, 100),
                ("sodium", -5, 100),
            ],
        ),
        make_food(
            2,
            "Food B",
            [
                ("protein", 20, 100),
                ("fiber", 4, 100),
                ("sodium", 0, 100),
            ],
        ),
    ]

    result = recommend_foods(
        foods,
        make_profile(goals=["high protein"]),
    )

    by_nutrient = result["nutrient_data_quality"]["by_nutrient"]

    assert by_nutrient["protein"]["total_records"] == 2
    assert by_nutrient["protein"]["available"] == 2
    assert by_nutrient["protein"]["coverage_percent"] == 100.0

    assert by_nutrient["fiber"]["total_records"] == 2
    assert by_nutrient["fiber"]["available"] == 1
    assert by_nutrient["fiber"]["missing"] == 1
    assert by_nutrient["fiber"]["coverage_percent"] == 50.0

    assert by_nutrient["sodium"]["total_records"] == 2
    assert by_nutrient["sodium"]["available"] == 1
    assert by_nutrient["sodium"]["invalid"] == 1
    assert by_nutrient["sodium"]["coverage_percent"] == 50.0
    assert by_nutrient["sodium"]["invalid_reasons"] == {
        "negative_amount": 1
    }

