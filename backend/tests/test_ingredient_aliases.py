from backend.scripts.import_recipe_datasets import normalize_ingredient_alias


def test_quantity_and_unit_are_removed():
    assert normalize_ingredient_alias("1 tablespoon Sunflower Oil") == "sunflower oil"


def test_fraction_and_unit_are_removed():
    assert normalize_ingredient_alias("1/2 teaspoon Turmeric powder (Haldi)") == "turmeric powder haldi"


def test_preparation_suffix_is_removed():
    assert normalize_ingredient_alias("4 cloves Garlic - finely chopped") == "garlic"


def test_distinct_ingredient_forms_remain_distinct():
    assert normalize_ingredient_alias("Coriander (Dhania) Leaves") != normalize_ingredient_alias(
        "Coriander (Dhania) Seeds"
    )


def test_synonym_alias_key_is_not_fuzzy():
    assert normalize_ingredient_alias("Cumin seeds (Jeera)") != normalize_ingredient_alias(
        "Chia seeds"
    )
