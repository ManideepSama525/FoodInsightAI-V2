
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from backend.app.models.food import Food
from backend.app.services.nutrition.nutrient_validation import nutrient_value_status

ZERO = Decimal("0")
SUPPORTED_MACROS = (
    "energy_kcal",
    "protein",
    "total_carbohydrate",
    "total_fat",
    "fiber",
    "total_sugars",
    "sodium",
)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _quality_fields(status: str) -> dict:
    if status == "valid":
        return {
            "data_status": "available",
            "data_quality_reason": None,
        }

    if status == "missing":
        return {
            "data_status": "missing",
            "data_quality_reason": "missing",
        }

    return {
        "data_status": "invalid",
        "data_quality_reason": status,
    }


def calculate_food_nutrition(
    food: Food,
    quantity_g: Decimal,
    quantity_source: str = "user_entered",
) -> dict:
    if quantity_g <= ZERO:
        raise ValueError("quantity_g must be greater than zero")
    if quantity_source not in ("user_entered", "estimated"):
        raise ValueError(
            "quantity_source must be 'user_entered' or 'estimated'"
        )

    factor = quantity_g / Decimal("100")
    nutrient_rows = []

    for nutrient in food.nutrients:
        status = nutrient_value_status(
            nutrient.amount,
            nutrient.basis_g,
        )

        amount = None
        if status == "valid":
            amount = _quantize(
                nutrient.amount
                * factor
                * (Decimal("100") / nutrient.basis_g)
            )

        nutrient_rows.append({
            "nutrient_key": nutrient.nutrient_key,
            "display_name": nutrient.display_name,
            "amount": amount,
            "unit": nutrient.unit,
            "source": getattr(nutrient, "source", None),
            "source_nutrient_id": getattr(nutrient, "source_nutrient_id", None),
            "derivation_code": getattr(nutrient, "derivation_code", None),
            "derivation_description": getattr(nutrient, "derivation_description", None),
            "derivation_source_description": getattr(nutrient, "derivation_source_description", None),
            **_quality_fields(status),
        })

    return {
        "food_id": food.id,
        "food_name": food.name,
        "quantity_g": _quantize(quantity_g),
        "quantity_source": quantity_source,
        "quantity_note": (
            "Quantity entered by the user."
            if quantity_source == "user_entered"
            else (
                "Approximate quantity supplied by the user; "
                "not measured from the image."
            )
        ),
        "nutrients": nutrient_rows,
    }


def aggregate_recipe_nutrition(
    ingredients: Iterable[tuple[Food, Decimal]],
) -> dict:
    sums: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    unknown_reasons: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for food, quantity_g in ingredients:
        if quantity_g <= ZERO:
            raise ValueError("Ingredient quantity must be greater than zero.")

        factor = quantity_g / Decimal("100")

        for nutrient in food.nutrients:
            key = (
                nutrient.nutrient_key,
                nutrient.display_name,
                nutrient.unit,
            )

            status = nutrient_value_status(
                nutrient.amount,
                nutrient.basis_g,
            )

            if status != "valid":
                unknown_reasons[key].add(status)
                continue

            sums[key] += (
                nutrient.amount
                * factor
                * (Decimal("100") / nutrient.basis_g)
            )

    rows = []

    for key in sorted(set(sums) | set(unknown_reasons)):
        reasons = unknown_reasons.get(key, set())

        if reasons:
            amount = None
            # Preserve every distinct reason when ingredients disagree.
            quality_reason = ",".join(sorted(reasons))
            data_status = (
                "missing" if reasons == {"missing"} else "invalid"
            )
        else:
            amount = _quantize(sums[key])
            quality_reason = None
            data_status = "available"

        rows.append({
            "nutrient_key": key[0],
            "display_name": key[1],
            "amount": amount,
            "unit": key[2],
            "data_status": data_status,
            "data_quality_reason": quality_reason,
        })

    return rows
