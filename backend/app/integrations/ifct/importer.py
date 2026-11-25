import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from backend.app.models.food import Food, FoodNutrient


class IFCTImportError(ValueError):
    pass


REQUIRED_COLUMNS = {
    "food_code", "food_name", "nutrient_key", "nutrient_name",
    "amount_per_100g", "unit",
}


def _parse_amount(raw: str) -> Decimal | None:
    value = raw.strip()
    if not value or value.casefold() in {"na", "n/a", "nd", "tr", "trace", "-", "null"}:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise IFCTImportError(f"Invalid nutrient amount: {raw!r}") from exc


def iter_ifct_foods(csv_path: Path) -> Iterator[Food]:
    """Read a user-supplied, licensed IFCT-derived CSV.

    Expected one row per food/nutrient. This does not download or redistribute
    IFCT data. Keep the original source and license with the supplied dataset.
    """
    if not csv_path.is_file():
        raise IFCTImportError(f"IFCT CSV file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise IFCTImportError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        current_code: str | None = None
        current_food: Food | None = None
        for row in reader:
            code = row["food_code"].strip()
            name = row["food_name"].strip()
            if not code or not name:
                raise IFCTImportError("food_code and food_name are required.")

            if current_code != code:
                if current_food is not None:
                    yield current_food
                current_code = code
                current_food = Food(
                    name=name,
                    normalized_name=" ".join(name.casefold().split()),
                    source="ifct",
                    external_id=code,
                    source_url="user-supplied IFCT dataset; see dataset license and attribution",
                )

            assert current_food is not None
            nutrient_key = row["nutrient_key"].strip()
            nutrient_name = row["nutrient_name"].strip()
            unit = row["unit"].strip()
            if not nutrient_key or not nutrient_name or not unit:
                raise IFCTImportError("nutrient_key, nutrient_name and unit are required.")
            current_food.nutrients.append(
                FoodNutrient(
                    nutrient_key=nutrient_key,
                    display_name=nutrient_name,
                    amount=_parse_amount(row["amount_per_100g"]),
                    unit=unit,
                    basis_g=Decimal("100"),
                    source="ifct",
                    source_nutrient_id=nutrient_key,
                )
            )
        if current_food is not None:
            yield current_food
