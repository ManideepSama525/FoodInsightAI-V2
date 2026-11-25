# Phase 7 — Integration and evaluation

## Connected workflows

The frontend now uses the API for local food catalog search, USDA search/import, portion calculation, recognition upload, recipe creation, and recipe listing. The catalog endpoint supports an empty query to provide the recipe ingredient selector with existing catalog records.

## Integration test coverage

`backend/tests/test_api_integration.py` uses an isolated in-memory SQLite database and FastAPI dependency overrides. It covers:
- local food search and portion scaling,
- listing catalog foods for recipe selection,
- recipe creation and per-serving nutrient totals,
- rejection of missing food IDs,
- explicit HTTP 503 when no trained recognition artifact is configured.

These are automated test cases authored for the project. Their passing status depends on running the test suite in the target environment.

## Manual integration checklist

1. Start the backend and verify `/api/v1/health` and `/docs`.
2. Start the frontend and verify the API status indicator.
3. Search a food in Nutrition; import one USDA record if the API key is configured.
4. Open the food detail and calculate a non-100 g portion.
5. Open Recipes; confirm imported/local foods appear in the ingredient selector.
6. Create a multi-ingredient recipe and compare full-recipe and per-serving values.
7. Upload a supported image. Before model training, the expected result is a clear model-not-configured response (HTTP 503), not a fabricated label.
8. Repeat with an actual trained artifact after model training and verify class-label order, preprocessing parity, and confidence threshold.

## Evaluation protocol

Do not report model accuracy until a held-out, leakage-resistant test set has been evaluated. Report top-1/top-5 accuracy, macro precision/recall/F1, per-class support, confusion matrix, and confidence calibration. Nutrition validation should compare selected catalog records and portion calculations against source records and hand-calculated examples. Keep dataset provenance and data licenses with the evaluation report.
