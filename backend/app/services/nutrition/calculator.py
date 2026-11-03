from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from backend.app.models.food import Food, FoodNutrient

ZERO = Decimal("0")
SUPPORTED_MACROS = ("energy_kcal", "protein", "total_carbohydrate", "total_fat", "fiber", "total_sugars", "sodium")

def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def calculate_food_nutrition(food: Food, quantity_g: Decimal) -> dict:
    if quantity_g <= ZERO:
        raise ValueError("quantity_g must be greater than zero")
    totals: dict[str, Decimal | None] = {}
    factor = quantity_g / Decimal("100")
    for nutrient in food.nutrients:
        if nutrient.amount is None:
            totals[nutrient.nutrient_key] = None
            continue
        if nutrient.basis_g <= ZERO:
            continue
        totals[nutrient.nutrient_key] = _quantize(nutrient.amount * factor * (Decimal("100") / nutrient.basis_g))
    return {
        "food_id": food.id,
        "food_name": food.name,
        "quantity_g": _quantize(quantity_g),
        "nutrients": [
            {"nutrient_key": n.nutrient_key, "display_name": n.display_name,
             "amount": totals.get(n.nutrient_key), "unit": n.unit}
            for n in food.nutrients
        ],
    }

def aggregate_recipe_nutrition(ingredients: Iterable[tuple[Food, Decimal]]) -> dict:
    sums: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    unknown: set[tuple[str, str, str]] = set()
    for food, quantity_g in ingredients:
        if quantity_g <= ZERO:
            raise ValueError("Ingredient quantity must be greater than zero.")
        factor = quantity_g / Decimal("100")
        for nutrient in food.nutrients:
            key = (nutrient.nutrient_key, nutrient.display_name, nutrient.unit)
            if nutrient.amount is None or nutrient.basis_g <= ZERO:
                unknown.add(key)
            else:
                sums[key] += nutrient.amount * factor * (Decimal("100") / nutrient.basis_g)
    rows = []
    for key in sorted(set(sums) | unknown):
        amount = None if key in unknown else _quantize(sums[key])
        rows.append({"nutrient_key": key[0], "display_name": key[1], "amount": amount, "unit": key[2]})
    return rows
