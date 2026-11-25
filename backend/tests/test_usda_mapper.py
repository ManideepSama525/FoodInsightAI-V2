from backend.app.integrations.usda.mapper import map_usda_food, map_usda_search_result


def test_usda_mapper_preserves_missing_values_and_source_provenance() -> None:
    food = map_usda_food({
        "fdcId": 123,
        "description": "Cooked lentils",
        "foodNutrients": [
            {
                "nutrient": {
                    "id": 1003,
                    "number": "203",
                    "name": "Protein",
                    "unitName": "g",
                },
                "amount": 9.02,
                "foodNutrientDerivation": {
                    "code": "A",
                    "description": "Analytical",
                    "foodNutrientSource": {
                        "description": "Analytical or derived from analytical",
                    },
                },
            },
            {
                "nutrient": {
                    "id": 1004,
                    "number": "204",
                    "name": "Total lipid",
                    "unitName": "g",
                },
                "amount": None,
            },
            {
                "nutrient": {
                    "id": 9999,
                    "number": "9999",
                    "name": "Unknown",
                    "unitName": "g",
                },
                "amount": 1,
            },
        ],
    })

    assert food.source == "usda_fdc"
    assert food.external_id == "123"
    assert food.normalized_name == "cooked lentils"
    assert len(food.nutrients) == 2

    protein = food.nutrients[0]
    assert protein.nutrient_key == "protein"
    assert float(protein.amount) == 9.02
    assert protein.source_nutrient_id == "1003"
    assert protein.derivation_code == "A"
    assert protein.derivation_description == "Analytical"
    assert protein.derivation_source_description == "Analytical or derived from analytical"

    fat = food.nutrients[1]
    assert fat.nutrient_key == "total_fat"
    assert fat.amount is None
    assert fat.source_nutrient_id == "1004"
    assert fat.derivation_code is None


def test_usda_mapper_uses_nutrient_id_not_nutrient_number() -> None:
    food = map_usda_food({
        "fdcId": 456,
        "description": "Foundation test food",
        "foodNutrients": [
            {
                "nutrient": {
                    "id": 1162,
                    "number": "401",
                    "name": "Vitamin C, total ascorbic acid",
                    "unitName": "mg",
                },
                "amount": 12.5,
                "foodNutrientDerivation": {
                    "code": "AS",
                    "description": "Summed",
                    "foodNutrientSource": {
                        "description": "Analytical or derived from analytical",
                    },
                },
            },
        ],
    })

    assert len(food.nutrients) == 1
    nutrient = food.nutrients[0]
    assert nutrient.nutrient_key == "vitamin_c"
    assert nutrient.source_nutrient_id == "1162"
    assert nutrient.derivation_code == "AS"


def test_usda_mapper_skips_missing_or_invalid_nutrient_ids() -> None:
    food = map_usda_food({
        "fdcId": 789,
        "description": "Test food",
        "foodNutrients": [
            {"nutrient": {"number": "203", "name": "Protein"}, "amount": 5},
            {"nutrient": {"id": "invalid", "number": "203"}, "amount": 5},
        ],
    })

    assert food.nutrients == []


def test_usda_search_mapper() -> None:
    result = map_usda_search_result({
        "fdcId": 42,
        "description": "Rice",
        "dataType": "SR Legacy",
    })
    assert result["fdc_id"] == 42
    assert result["description"] == "Rice"