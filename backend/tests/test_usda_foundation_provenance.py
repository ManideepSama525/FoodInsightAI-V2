
import json

import pytest

from backend.app.services.nutrition.import_usda_foundation_provenance import (
    read_provenance_json,
)


def test_reads_foundation_derivation_metadata(tmp_path):
    source = {
        "FoundationFoods": [
            {
                "fdcId": 123,
                "foodNutrients": [
                    {
                        "nutrient": {"id": 1003, "number": "1003"},
                        "foodNutrientDerivation": {
                            "code": "A",
                            "description": "Analytical",
                            "foodNutrientSource": {
                                "id": 1,
                                "code": "1",
                                "description": "Analytical source",
                            },
                        },
                    }
                ],
            }
        ]
    }
    path = tmp_path / "foundation.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    result = read_provenance_json(path)

    assert result[("123", "1003")] == {
        "derivation_code": "A",
        "derivation_description": "Analytical",
        "derivation_source_description": "Analytical source",
    }


def test_missing_derivation_remains_null(tmp_path):
    source = {
        "FoundationFoods": [
            {
                "fdcId": 123,
                "foodNutrients": [
                    {"nutrient": {"id": 1003, "number": "1003"}}
                ],
            }
        ]
    }
    path = tmp_path / "foundation.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    result = read_provenance_json(path)

    assert result[("123", "1003")] == {
        "derivation_code": None,
        "derivation_description": None,
        "derivation_source_description": None,
    }


def test_duplicate_food_nutrient_pair_is_rejected(tmp_path):
    item = {"nutrient": {"id": 1003}}
    source = {
        "FoundationFoods": [
            {
                "fdcId": 123,
                "foodNutrients": [item, item],
            }
        ]
    }
    path = tmp_path / "foundation.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate source nutrient pair"):
        read_provenance_json(path)


def test_invalid_json_structure_is_rejected(tmp_path):
    path = tmp_path / "foundation.json"
    path.write_text('{"foods": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="FoundationFoods"):
        read_provenance_json(path)
