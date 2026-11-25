# Nutrition data integration

## USDA FoodData Central
The API adapter supports food search and food-detail retrieval. Configure `USDA_API_KEY` in the local `.env` file. The key is never stored in source control. USDA data are attributed using the FDC identifier and food-detail URL.

Endpoints:
- `GET /api/v1/nutrition/foods?q=lentils` — search imported local catalog
- `GET /api/v1/nutrition/foods/usda/search?q=lentils` — live USDA search
- `POST /api/v1/nutrition/foods/usda/{fdc_id}/import` — import a USDA food detail record

## Nutrient semantics
Known USDA nutrient identifiers are mapped to stable internal keys. Unrecognized nutrient identifiers are skipped rather than guessed. A missing amount remains `null`; it is not interpreted as zero. Original source units are retained. The `basis_g` field records the 100 g basis for imported source values. Any unit conversion must be explicit and tested in a later calculation layer.

## IFCT
The importer accepts a user-supplied CSV derived from an IFCT dataset that the user is authorized to use. It does not download, bundle, or redistribute IFCT data. Required columns:

`food_code,food_name,nutrient_key,nutrient_name,amount_per_100g,unit`

Use one row per food/nutrient. `NA`, `ND`, `trace`, `-` and blank amounts are retained as missing (`null`), not zero. Keep the original dataset, license and attribution information alongside the local source data; do not commit restricted datasets to Git.

## Operational notes
USDA requests require internet access and a valid API key. External API failure is returned as a controlled 502 response. Live API calls are not part of the offline unit tests.
