# Knowledge graph implementation handoff

The current release stores food, nutrient, recipe and ingredient relationships in a relational SQLAlchemy database. A graph database and populated knowledge graph have **not** been implemented in this phase.

## Recommended scope

Use a separate graph layer for semantic relationships and reasoning; keep the relational database as the source of truth for catalog records, measured nutrient values, recipes and transactional workflows.

### Candidate node types

- `Food` — canonical food identity, common names, category, preparation state and source references.
- `Nutrient` — nutrient identity, canonical unit and classification.
- `Recipe` — recipe identity, serving count and provenance.
- `IngredientUse` — recipe-specific quantity and unit; model as an edge with properties or a node if traceability demands it.
- `FoodCategory` — controlled taxonomy term.
- `Allergen` — controlled allergen identity.
- `DietaryPattern` — explicitly defined dietary classification.

### Candidate relationships

- `(Food)-[:HAS_NUTRIENT {amount, unit, basis_g, source_id}]->(Nutrient)`
- `(Recipe)-[:USES {quantity, unit}]->(Food)`
- `(Food)-[:IN_CATEGORY]->(FoodCategory)`
- `(Food)-[:CONTAINS_ALLERGEN]->(Allergen)`
- `(Food)-[:ALTERNATIVE_TO {basis, confidence, evidence_ref}]->(Food)`

Do not create inferred allergen or dietary claims without a traceable evidence source. A missing nutrient amount must remain unknown; it must not be represented as zero.

## Implementation sequence

1. Select Neo4j or another graph store after reviewing deployment constraints and academic requirements.
2. Define stable IDs shared with relational Food/Nutrient/Recipe records.
3. Define ontology, units, preparation-state vocabulary, provenance and versioning.
4. Build an idempotent ETL from relational records; preserve source IDs and timestamps.
5. Add constraints and indexes; document duplicate resolution and update/delete propagation.
6. Add graph query service behind an adapter; do not expose arbitrary Cypher from the API.
7. Test ingestion idempotency, referential integrity, provenance, unknown values and query correctness.
8. Evaluate graph-supported use cases against a relational baseline and report measurable results.

## Required evidence for the academic report

Document the graph schema, selected database and rationale, ETL mapping, representative queries, sample graph data with licenses, correctness tests, query latency, limitations and screenshots/exported visualizations. Do not claim a populated graph or reasoning results until these are implemented and evaluated.
