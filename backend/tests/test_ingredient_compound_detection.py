import pytest

from backend.scripts.import_recipe_datasets import (
    normalize_ingredient_alias,
    is_compound_ingredient_for_review,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2 cloves Garlic - finely chopped", "garlic"),
        ("1 tablespoon Garlic - minced", "garlic"),
        ("Sunflower Oil - for deep frying", "sunflower oil"),
        ("2 tablespoons Extra Virgin Olive Oil", "extra virgin olive oil"),
    ],
)
def test_simple_ingredients_remain_eligible(raw, expected):
    assert not is_compound_ingredient_for_review(raw)
    assert normalize_ingredient_alias(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Garlic - minced, Sesame seeds (Til seeds) - Roasted",
        "Garlic - finely chopped (or garlic paste)",
        "Garlic - finely chopped (or a teaspoon if garlic powder)",
        "Garlic - minced, Dried oregano - for seasoning",
        "Sunflower Oil - as required, pinch Sugar",
        "Sunflower Oil - as required (ghee)",
    ],
)
def test_compound_ingredients_are_rejected(raw):
    assert is_compound_ingredient_for_review(raw)
