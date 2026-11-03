# Nutrition calculations and recipe intelligence

## Food portion calculation

`GET /api/v1/nutrition/foods/{food_id}/calculate?quantity_g=150` scales stored nutrient values from their recorded `basis_g` to the requested edible weight in grams. Nutrients with missing source values remain `null`; the system does not convert missing, trace, or unknown values to zero.

## Recipe API

- `POST /api/v1/recipes` creates a recipe from existing catalog food IDs and gram quantities.
- `GET /api/v1/recipes` lists recipes.
- `GET /api/v1/recipes/{recipe_id}` returns a recipe.

Example request:

```json
{
  "name": "Simple rice bowl",
  "servings": 2,
  "instructions": "Combine cooked ingredients.",
  "ingredients": [
    {"food_id": 12, "quantity_g": 150},
    {"food_id": 18, "quantity_g": 80}
  ]
}
```

Responses include nutrient totals for the full recipe and per serving. Ingredient weights are currently accepted in grams only. Volume-to-weight conversions are deliberately not guessed because ingredient density varies.

## Calculation boundaries

- Values are calculated from the catalog records currently stored in the database.
- Nutrient units are retained as supplied by the source; values with different units are not merged into one total.
- If any ingredient has an unknown value for a nutrient, the aggregate for that nutrient is `null`, rather than an understated partial sum.
- Recipe totals are arithmetic estimates. Cooking yield, moisture loss, nutrient retention, edible portion adjustments, and laboratory variation are not modelled yet.
- Energy is reported only when the source provides an energy nutrient; no inferred calorie calculation is substituted.
