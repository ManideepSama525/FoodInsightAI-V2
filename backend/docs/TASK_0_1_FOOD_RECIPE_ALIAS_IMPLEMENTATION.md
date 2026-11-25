# Task 0.1 — Food–Recipe Links and Recognition Aliases

## Changes
- Added `FoodRecipe`, a SQL association with a unique `(food_id, recipe_id)` pair, source, JSON provenance, and active flag.
- Added `RecognitionAlias`, with unique `(model_source, normalized_label)` mappings to canonical Food records.
- Added exact Unicode-normalized alias lookup. Model-specific aliases take precedence over `any`; ambiguous matches return no result.
- Recognition responses now include `canonical_food_id` and `canonical_food_name` when an exact curated alias exists.
- Added Alembic revision `0006_food_recipe_and_recognition_aliases`.
- Neo4j sync now creates `(Food)-[:HAS_RECIPE]->(Recipe)` with source/provenance metadata.
- Both shared recipe loading and association loading explicitly filter `Recipe.user_id IS NULL`.
- Food neighborhood responses include associated shared recipes.

## Data and safety
- No aliases or Food–Recipe associations are pre-seeded; no mappings are inferred from labels or existing private recipes.
- Private recipes remain excluded from graph recipe snapshots and HAS_RECIPE association snapshots.
- Existing SQL rows are not rewritten by the migration.

## Verification
- Python compilation: passed.
- SQLAlchemy mapper registration and SQLite metadata DDL: passed.
- Model-scoped exact alias resolution and unknown-label behavior: passed.
- Full pytest collection could not run in the packaging environment because the `pwdlib` dependency is absent. Run the project test suite in the existing Docker/venv environment before applying the migration to the active database.
