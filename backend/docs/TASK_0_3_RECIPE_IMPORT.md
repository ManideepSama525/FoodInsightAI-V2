# Task 0.3 — Recipe dataset import

## Scope
This importer reads the Indian Archana's Kitchen-derived CSV and the supplied 13k recipe CSV. It reuses `Recipe`, `RecipeIngredient`, `IngredientAlias`, `Dish`, and `DishRecipe`. It does not train or modify recognition models.

## Important rights status
The Indian dataset README says its content was created from Archana's Kitchen and uses translated fields. The README itself does not establish a redistribution license. The 13k dataset's rights are also not established by the project files. The importer records `license_unverified_review_required` and attribution metadata. Do not redistribute imported recipe text or make it public until rights are independently verified.

## Safety / data rules
- Recipes imported from datasets use `user_id = NULL` (shared catalog).
- Existing private recipes (`user_id != NULL`) are never queried for import matching, overwritten, or exported.
- Recipe identity is `(source, external_id)`; rerunning the importer updates the same source record.
- Ingredient names and original text are preserved.
- Exact normalized name matching against existing `foods.name` only; no fuzzy/semantic mapping.
- Quantities are parsed only when an explicit decimal number and unit are present. No conversion to grams is performed.
- Ingredient quantity may be NULL. Only a later validated gram conversion may be used for nutrition.
- `DishRecipe` is created only when the complete normalized recipe title exactly matches an active canonical Dish name or an explicitly curated full-title alias. Ingredient overlap alone never creates a dish association. Legacy `FoodRecipe` records are not created or modified by this importer.
- Dry-run is default. `--apply` is required to commit.

## Migration
Apply `0007_recipe_import_provenance` only after taking a database backup:
`docker compose exec -T backend alembic upgrade head`

## Dry-run examples
Inside the backend container, make the dataset files accessible via a mounted path, then:
```bash
python -m backend.scripts.import_recipe_datasets \
  --indian-csv /data/IndianFoodDatasetCSV.csv \
  --international-csv /data/13k-recipes.csv
```
The command defaults to rollback/dry-run. Add `--apply` only after reviewing output.

## Limitations to address in subsequent verification
- Quantity parser intentionally handles a conservative subset of units and does not convert cups/spoons/pieces to grams.
- Recipe title class matching is an initial rule-based coverage mechanism, not a manual relevance certification.
- Existing recipe API nutrition serializer must be updated to exclude non-gram or missing quantities and expose calculation completeness before imported records are exposed as nutrition-complete.

## Ingredient parsing safeguards

The Indian Archana CSV stores ingredient lists as comma-separated text rather than
Python-list values. The importer uses `backend.scripts.ingredient_parser` to split
only at conservative boundaries: an explicit quantity-like prefix or a known
unquantified ingredient starter. Descriptive comma fragments such as `finely
chopped` remain attached to the preceding ingredient. Ambiguous fragments are
kept together for review rather than guessed. The international 13k source uses
Python-list-like cells and is parsed as a list where possible.

Run parser tests with:

```powershell
python -m pytest backend/tests/test_recipe_ingredient_parser.py -q
```

This parser reduces malformed splits but cannot guarantee perfect segmentation
for every free-text ingredient cell. Review the dry-run ingredient samples and
mapping coverage before applying imports.


## Current architecture correction

The importer now resolves recipe titles against active `Dish` records and creates
`DishRecipe` associations. It no longer creates legacy `FoodRecipe` associations.
The Indian source's original Hindi title, ingredients, and instructions are retained
in `Recipe.source_metadata` alongside the translated fields. Dataset rights remain
unverified; attribution is retained and public redistribution is not authorized
by this importer.
