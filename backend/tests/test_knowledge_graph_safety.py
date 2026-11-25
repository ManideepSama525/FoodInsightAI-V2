from backend.app.services.knowledge_graph import (
    _build_unambiguous_ingredient_food_rows,
    _normalize_ingredient_name,
)


def test_ingredient_mapping_keeps_single_unambiguous_food_target():
    rows = _build_unambiguous_ingredient_food_rows([
        ("rice", 10),
        ("rice", 10),
        ("lentil", 20),
    ])

    assert rows == [
        {"normalized_name": "lentil", "food_id": 20},
        {"normalized_name": "rice", "food_id": 10},
    ]


def test_ingredient_mapping_rejects_conflicting_food_targets():
    rows = _build_unambiguous_ingredient_food_rows([
        ("milk", 10),
        ("milk", 11),
        ("rice", 20),
    ])

    assert rows == [{"normalized_name": "rice", "food_id": 20}]


def test_ingredient_mapping_ignores_empty_names_and_missing_food_ids():
    rows = _build_unambiguous_ingredient_food_rows([
        ("", 10),
        ("water", None),
        ("salt", 30),
    ])

    assert rows == [{"normalized_name": "salt", "food_id": 30}]


def test_ingredient_name_normalization_uses_nfkc_casefold_and_whitespace():
    assert _normalize_ingredient_name("  ＲＩＣＥ\t flour  ") == "rice flour"
    assert _normalize_ingredient_name("Café") == "café"
    assert _normalize_ingredient_name(None) == ""
