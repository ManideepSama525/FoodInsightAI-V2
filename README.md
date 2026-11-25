# Task 0.3 — SQLite-safe migration 0009 correction

The first attempt applied migrations 0007 and 0008, created some 0009 tables/columns,
then failed when SQLite rejected `ALTER TABLE ... ADD CONSTRAINT`.

Current expected Alembic revision: `0008_ingredient_aliases`.

## Install
Extract into the project root, preserving folders and replacing the existing
`backend/migrations/versions/0009_dish_knowledge_graph.py`.

Do not restore the pre-migration backup: migrations 0007/0008 succeeded and the
replacement migration is written to resume from the partially changed 0009 schema.

## Verify before retry
```powershell
docker compose exec -T backend alembic current
```
It should still report `0008_ingredient_aliases`.

## Apply
```powershell
docker compose build backend
docker compose up -d backend
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current
```
Expected: `0009_dish_knowledge_graph (head)`.

This migration checks for tables, columns, indexes and FK before creating them.
SQLite batch mode is used to add the recognition_aliases.dish_id foreign key.
No rows are seeded and no recipe data is imported. Do not run Neo4j sync yet.

If the migration fails again, stop and capture the full error; do not rerun blindly.
