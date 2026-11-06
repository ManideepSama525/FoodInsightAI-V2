from decimal import Decimal
from types import SimpleNamespace

from backend.app.services.nutrition.calculator import aggregate_recipe_nutrition, calculate_food_nutrition

def nutrient(key, amount, unit="g", basis="100"):
    return SimpleNamespace(
        nutrient_key=key, display_name=key, amount=None if amount is None else Decimal(amount),
        unit=unit, basis_g=Decimal(basis),
    )

def test_food_calculation_scales_from_100g_basis():
    food = SimpleNamespace(id=3, name="Cooked rice", nutrients=[nutrient("protein", "2.5")])
    result = calculate_food_nutrition(food, Decimal("150"))
    assert result["nutrients"][0]["amount"] == Decimal("3.75")

def test_unknown_nutrient_value_remains_unknown():
    food = SimpleNamespace(id=1, name="Food", nutrients=[nutrient("protein", None)])
    result = calculate_food_nutrition(food, Decimal("50"))
    assert result["nutrients"][0]["amount"] is None

def test_recipe_aggregation_sums_ingredients():
    food_a = SimpleNamespace(nutrients=[nutrient("protein", "10")])
    food_b = SimpleNamespace(nutrients=[nutrient("protein", "5")])
    rows = aggregate_recipe_nutrition([(food_a, Decimal("100")), (food_b, Decimal("200"))])
    assert rows[0]["amount"] == Decimal("20.00")


def test_food_calculation_records_user_entered_quantity():
    food = SimpleNamespace(id=3, name="Cooked rice", nutrients=[nutrient("protein", "2.5")])
    result = calculate_food_nutrition(food, Decimal("150"))
    assert result["quantity_source"] == "user_entered"
    assert result["quantity_note"] == "Quantity entered by the user."


def test_food_calculation_marks_estimated_quantity_as_unmeasured():
    food = SimpleNamespace(id=3, name="Cooked rice", nutrients=[nutrient("protein", "2.5")])
    result = calculate_food_nutrition(food, Decimal("150"), "estimated")
    assert result["quantity_source"] == "estimated"
    assert "not measured from the image" in result["quantity_note"]


def test_food_calculation_rejects_unknown_quantity_source():
    import pytest

    food = SimpleNamespace(id=3, name="Cooked rice", nutrients=[nutrient("protein", "2.5")])
    with pytest.raises(ValueError, match="quantity_source"):
        calculate_food_nutrition(food, Decimal("150"), "image_measured")