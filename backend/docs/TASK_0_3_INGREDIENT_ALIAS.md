# Task 0.3 — IngredientAlias implementation

## Scope
- Adds `IngredientAlias`, separate from recognition classifier aliases.
- An alias maps to a canonical `Food` only when `status='approved'` and `food_id` is populated.
- `review_required` and `rejected` records are never used by nutrition mapping.
- Importer preserves raw source ingredient text and does not infer gram weights.
- Exact canonical-name matching remains available as a distinct fallback.
- Fuzzy similarity is not used by the importer.
- Adds a read-only coverage audit.

## Migration
`0008_ingredient_aliases` follows `0007_recipe_import_provenance`.

## Alias fields
- `alias`, `normalized_alias`
- `food_id`: populated only for approved mapping
- `candidate_food_id`: optional review suggestion, not used by importer
- `status`: `approved`, `review_required`, or `rejected`
- `source`, `provenance`

A unique constraint prevents two aliases from claiming the same normalized key.

## Dry-run audit
Use `python -m backend.scripts.audit_ingredient_aliases --indian-csv PATH`.
The report shows exact canonical mappings, approved alias mappings, and frequent unmapped identities.

## Safety
- No aliases are pre-seeded by this patch. Candidate similarity outputs from earlier audits are not trusted as mappings.
- No live database migration or recipe import is included.
- Run migration and audit against a disposable database first.
- Recipe datasets have unverified redistribution rights; source provenance is retained.
- Private recipes remain protected by the existing importer conflict check.

## Important limitation
`FoodRecipe` currently points from a canonical `Food` record to a recipe. This patch does not redefine that relation as a dish entity. A separate dish catalogue/association design remains necessary before linking classifier dish labels to recipes.
