from backend.app.integrations.usda.mapper import map_usda_food, map_usda_search_result


def test_usda_mapper_preserves_missing_values_and_source_provenance() -> None:
    food = map_usda_food({
        "fdcId": 123,
        "description": "Cooked lentils",
        "foodNutrients": [
            {"nutrient": {"number": 1003, "name": "Protein", "unitName": "g"}, "amount": 9.02},
            {"nutrient": {"number": 1004, "name": "Total lipid", "unitName": "g"}, "amount": None},
            {"nutrient": {"number": 9999, "name": "Unknown", "unitName": "g"}, "amount": 1},
        ],
    })
    assert food.source == "usda_fdc"
    assert food.external_id == "123"
    assert food.normalized_name == "cooked lentils"
    assert len(food.nutrients) == 2
    assert float(food.nutrients[0].amount) == 9.02
    assert food.nutrients[1].amount is None


def test_usda_search_mapper() -> None:
    result = map_usda_search_result({"fdcId": 42, "description": "Rice", "dataType": "SR Legacy"})
    assert result["fdc_id"] == 42
    assert result["description"] == "Rice"
