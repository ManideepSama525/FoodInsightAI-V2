from decimal import Decimal, InvalidOperation
from typing import Any

from backend.app.models.food import Food, FoodNutrient

# USDA nutrient numbers are stable identifiers in FoodData Central records.
NUTRIENT_MAP: dict[int, tuple[str, str]] = {
    1008: ("energy_kcal", "kcal"),
    1003: ("protein", "g"),
    1004: ("total_fat", "g"),
    1005: ("carbohydrate", "g"),
    1079: ("fiber", "g"),
    2000: ("total_sugars", "g"),
    1093: ("sodium", "mg"),
    1258: ("saturated_fat", "g"),
    1253: ("cholesterol", "mg"),
    1092: ("potassium", "mg"),
    1087: ("calcium", "mg"),
    1089: ("iron", "mg"),
    1106: ("vitamin_a", "µg"),
    1162: ("vitamin_c", "mg"),
}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def map_usda_food(payload: dict[str, Any]) -> Food:
    fdc_id = payload.get("fdcId")
    if fdc_id is None:
        raise ValueError("USDA food detail is missing fdcId.")
    name = str(payload.get("description") or "Unnamed food").strip()
    food = Food(
        name=name,
        normalized_name=" ".join(name.casefold().split()),
        category=payload.get("foodCategory", {}).get("description")
        if isinstance(payload.get("foodCategory"), dict)
        else None,
        source="usda_fdc",
        external_id=str(fdc_id),
        source_url=f"https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients",
        description=payload.get("additionalDescriptions"),
    )

    seen: set[str] = set()
    for item in payload.get("foodNutrients", []):
        nutrient = item.get("nutrient") if isinstance(item.get("nutrient"), dict) else item
        number = nutrient.get("number")
        try:
            number = int(number)
        except (TypeError, ValueError):
            continue
        if number not in NUTRIENT_MAP:
            continue

        key, canonical_unit = NUTRIENT_MAP[number]
        if key in seen:
            continue
        seen.add(key)
        raw_value = item.get("amount", item.get("value"))
        amount = _decimal_or_none(raw_value)
        source_unit = nutrient.get("unitName")
        # Preserve canonical units only when USDA's unit agrees. Unknown unit
        # variants are retained as reported rather than silently converted.
        unit = canonical_unit if not source_unit else str(source_unit)
        food.nutrients.append(
            FoodNutrient(
                nutrient_key=key,
                display_name=str(nutrient.get("name") or key.replace("_", " ").title()),
                amount=amount,
                unit=unit,
                basis_g=Decimal("100"),
                source="usda_fdc",
                source_nutrient_id=str(number),
            )
        )
    return food


def map_usda_search_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fdc_id": item.get("fdcId"),
        "description": item.get("description"),
        "data_type": item.get("dataType"),
        "brand_owner": item.get("brandOwner"),
        "brand_name": item.get("brandName"),
        "food_category": item.get("foodCategory"),
        "publication_date": item.get("publishedDate"),
    }
