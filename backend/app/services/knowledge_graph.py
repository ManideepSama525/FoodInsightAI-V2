from __future__ import annotations

import json
import unicodedata
from collections import defaultdict

from neo4j import GraphDatabase
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.config import get_settings
from backend.app.models.food import Food, FoodNutrient
from backend.app.models.dish import Dish, DishRecipe
from backend.app.models.recipe import Recipe
from backend.app.services.nutrition.nutrient_validation import nutrient_value_status

settings = get_settings()


def _normalize_ingredient_name(value: str | None) -> str:
    """Normalize display text for stable Ingredient node identity."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def _build_unambiguous_ingredient_food_rows(candidates):
    """Return one Food mapping per ingredient name only when all approved
    occurrences agree on the same canonical Food ID.

    `candidates` is an iterable of (normalized_name, food_id) pairs.
    Ambiguous names are deliberately left unresolved.
    """
    food_ids_by_name = defaultdict(set)
    for normalized_name, food_id in candidates:
        if normalized_name and food_id is not None:
            food_ids_by_name[normalized_name].add(food_id)

    return [
        {"normalized_name": name, "food_id": next(iter(food_ids))}
        for name, food_ids in sorted(food_ids_by_name.items())
        if len(food_ids) == 1
    ]


class KnowledgeGraph:
    """Synchronize SQL-authoritative food knowledge without deleting nodes.

    This synchronizer owns only relationships tagged source_system=SOURCE.
    It never deletes graph nodes. Public recipe content that was previously
    synchronized but is no longer in the public SQL snapshot is sanitized.
    """

    SOURCE = "foodinsightai_sql"

    def __init__(self) -> None:
        self._driver = None
        if settings.knowledge_graph_enabled and settings.neo4j_password:
            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
                connection_timeout=5,
                max_connection_pool_size=20,
            )

    @property
    def driver(self):
        if self._driver is None:
            raise RuntimeError("Knowledge graph is disabled or not configured")
        return self._driver

    @property
    def enabled(self) -> bool:
        return self._driver is not None

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def verify(self) -> bool:
        if not self.enabled:
            return False
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def initialize(self) -> None:
        if not self.enabled:
            return
        statements = [
            "CREATE CONSTRAINT food_relational_id IF NOT EXISTS FOR (n:Food) REQUIRE n.food_id IS UNIQUE",
            "CREATE CONSTRAINT nutrient_key IF NOT EXISTS FOR (n:Nutrient) REQUIRE n.key IS UNIQUE",
            "CREATE CONSTRAINT recipe_relational_id IF NOT EXISTS FOR (n:Recipe) REQUIRE n.recipe_id IS UNIQUE",
            "CREATE CONSTRAINT ingredient_name IF NOT EXISTS FOR (n:Ingredient) REQUIRE n.normalized_name IS UNIQUE",
            "CREATE CONSTRAINT dish_relational_id IF NOT EXISTS FOR (n:Dish) REQUIRE n.dish_id IS UNIQUE",
        ]
        with self._driver.session(database=settings.neo4j_database) as session:
            for statement in statements:
                session.run(statement).consume()

    def food_neighborhood(self, food_id: int) -> dict | None:
        # Read-only lookup; retain nutrient measurement and source provenance.
        if not self.enabled:
            raise RuntimeError("Knowledge graph is disabled or not configured")

        query = (
            "MATCH (f:Food {food_id: $food_id}) "
            "OPTIONAL MATCH (f)-[rel:HAS_NUTRIENT]->(n:Nutrient) "
            "RETURN properties(f) AS food, "
            "collect(CASE WHEN n IS NULL THEN null ELSE {"
            "name: n.name, key: n.key, amount: rel.amount, "
            "unit: rel.unit, basis_g: rel.basis_g, source: rel.source, "
            "source_nutrient_id: rel.source_nutrient_id, "
            "derivation_code: properties(rel)['derivation_code'], "
            "derivation_description: properties(rel)['derivation_description'], "
            "derivation_source_description: properties(rel)['derivation_source_description']"
            "} END) AS nutrients"
        )

        with self.driver.session(database=settings.neo4j_database) as session:
            record = session.run(query, food_id=food_id).single()

        if record is None or record.get("food") is None:
            return None

        return {
            "food": dict(record["food"]),
            "nutrients": [
                dict(item)
                for item in (record.get("nutrients") or [])
                if item is not None
            ],
            "recipes": [],
        }

    def sync(self, db: Session, dry_run: bool = False) -> dict[str, int]:
        if not self.enabled:
            raise RuntimeError("Knowledge graph is disabled or not configured")

        foods = db.scalars(select(Food).options(selectinload(Food.nutrients))).all()
        food_rows, nutrient_rows = [], []
        for food in foods:
            food_rows.append({
                "food_id": food.id,
                "name": food.name,
                "normalized_name": food.normalized_name,
                "category": food.category,
                "source": food.source,
                "external_id": food.external_id,
                "source_url": food.source_url,
                "description": food.description,
            })
            for nutrient in food.nutrients:
                if nutrient_value_status(nutrient.amount, nutrient.basis_g) == "valid":
                    nutrient_rows.append({
                        "food_id": food.id,
                        "key": nutrient.nutrient_key,
                        "name": nutrient.display_name,
                        "amount": float(nutrient.amount),
                        "unit": nutrient.unit,
                        "basis_g": float(nutrient.basis_g),
                        "source": nutrient.source,
                        "source_nutrient_id": nutrient.source_nutrient_id,
                        "derivation_code": getattr(nutrient, "derivation_code", None),
                        "derivation_description": getattr(nutrient, "derivation_description", None),
                        "derivation_source_description": getattr(nutrient, "derivation_source_description", None),
                    })

        # Active Dish records are canonical entities in their own right.
        # They must enter the graph even when no public recipes are associated.
        active_dishes = db.scalars(
            select(Dish).where(Dish.is_active.is_(True))
        ).all()
        dish_rows = {
            dish.id: {
                "dish_id": dish.id,
                "name": dish.name,
                "normalized_name": dish.normalized_name,
                "category": dish.category,
                "source": dish.source,
                "provenance_json": json.dumps(
                    dish.provenance or {}, ensure_ascii=False, sort_keys=True
                ),
            }
            for dish in active_dishes
        }

        # SQL is authoritative. Only active, globally shared recipes linked to
        # active dishes through active associations enter the public recipe snapshot.
        associations = db.scalars(
            select(DishRecipe)
            .join(Recipe, Recipe.id == DishRecipe.recipe_id)
            .join(DishRecipe.dish)
            .where(
                DishRecipe.is_active.is_(True),
                Recipe.user_id.is_(None),
                DishRecipe.dish.has(Dish.is_active.is_(True)),
            )
            .options(
                selectinload(DishRecipe.dish),
                selectinload(DishRecipe.recipe).selectinload(Recipe.ingredients),
            )
        ).unique().all()

        recipe_rows, dish_recipe_rows = {}, []
        ingredient_rows = []
        ingredient_mapping_candidates = []

        for association in associations:
            dish, recipe = association.dish, association.recipe
            dish_rows[dish.id] = {
                "dish_id": dish.id,
                "name": dish.name,
                "normalized_name": dish.normalized_name,
                "category": dish.category,
                "source": dish.source,
                "provenance_json": json.dumps(
                    dish.provenance or {}, ensure_ascii=False, sort_keys=True
                ),
            }
            recipe_rows[recipe.id] = {
                "recipe_id": recipe.id,
                "name": recipe.name,
                "servings": recipe.servings,
                "instructions": recipe.instructions,
            }
            dish_recipe_rows.append({
                "dish_id": dish.id,
                "recipe_id": recipe.id,
                "source": association.source,
                "provenance_json": json.dumps(
                    association.provenance or {}, ensure_ascii=False, sort_keys=True
                ),
            })

            for item in recipe.ingredients:
                normalized = _normalize_ingredient_name(item.ingredient_name)
                if not normalized:
                    continue
                ingredient_rows.append({
                    "recipe_id": recipe.id,
                    "normalized_name": normalized,
                    "name": item.ingredient_name,
                    "quantity": float(item.quantity) if item.quantity is not None else None,
                    "unit": item.unit,
                    "mapping_status": item.mapping_status,
                    "quantity_status": item.quantity_status,
                })
                if (
                    item.food_id is not None
                    and item.mapping_status in {"approved_alias", "exact_name"}
                ):
                    ingredient_mapping_candidates.append((normalized, item.food_id))

        ingredient_food_rows = _build_unambiguous_ingredient_food_rows(
            ingredient_mapping_candidates
        )

        food_ids = [row["food_id"] for row in food_rows]
        nutrient_pairs = [
            {"food_id": row["food_id"], "key": row["key"]}
            for row in nutrient_rows
        ]
        recipe_ids = list(recipe_rows)
        dish_ids = list(dish_rows)
        dr_pairs = [
            {"dish_id": row["dish_id"], "recipe_id": row["recipe_id"]}
            for row in dish_recipe_rows
        ]
        ri_pairs = [
            {
                "recipe_id": row["recipe_id"],
                "normalized_name": row["normalized_name"],
            }
            for row in ingredient_rows
        ]
        mapping_pairs = [
            {
                "normalized_name": row["normalized_name"],
                "food_id": row["food_id"],
            }
            for row in ingredient_food_rows
        ]

        if not food_rows:
            raise RuntimeError(
                "Refusing graph sync: canonical Food snapshot is empty"
            )

        snapshot_counts = {
            "foods_synced": len(food_rows),
            "nutrient_relationships_synced": len(nutrient_rows),
            "dishes_synced": len(dish_rows),
            "recipes_synced": len(recipe_rows),
            "dish_recipe_relationships_synced": len(dish_recipe_rows),
            "ingredient_mentions_synced": len(ingredient_rows),
            "ingredient_food_relationships_synced": len(ingredient_food_rows),
        }

        # A dry run builds and validates the SQL snapshot only. It does not
        # initialize constraints, open a Neo4j session, or write to the graph.
        if dry_run:
            return {"dry_run": True, **snapshot_counts}

        # Schema initialization is deliberately outside the data transaction.
        # It is idempotent and only occurs for an explicitly requested live sync.
        self.initialize()

        with self._driver.session(database=settings.neo4j_database) as session:
            tx = session.begin_transaction()

            def run(query: str, **params):
                # All data upserts, sanitization and reconciliation statements
                # now share this one transaction.
                tx.run(query, **params).consume()

            try:

                # Upsert canonical Food and Nutrient data.
                run("""
                    UNWIND $rows AS row
                    MERGE (f:Food {food_id: row.food_id})
                    SET f.name=row.name, f.normalized_name=row.normalized_name,
                        f.category=row.category, f.source=row.source,
                        f.external_id=row.external_id, f.source_url=row.source_url,
                        f.description=row.description
                """, rows=food_rows)

                if nutrient_rows:
                    run("""
                        UNWIND $rows AS row
                        MATCH (f:Food {food_id: row.food_id})
                        MERGE (n:Nutrient {key: row.key})
                        SET n.name=row.name
                        MERGE (f)-[r:HAS_NUTRIENT]->(n)
                        // Tag only relationships created by this synchronizer.
                        // Existing untagged legacy relationships remain unowned.
                        ON CREATE SET r.source_system=$source
                        SET r.amount=row.amount, r.unit=row.unit, r.basis_g=row.basis_g,
                            r.source=row.source, r.source_nutrient_id=row.source_nutrient_id,
                            r.derivation_code=row.derivation_code,
                            r.derivation_description=row.derivation_description,
                            r.derivation_source_description=row.derivation_source_description
                    """, rows=nutrient_rows, source=self.SOURCE)

                if dish_rows:
                    run("""
                        UNWIND $rows AS row
                        MERGE (d:Dish {dish_id: row.dish_id})
                        SET d.name=row.name, d.normalized_name=row.normalized_name,
                            d.category=row.category, d.source=row.source,
                            d.provenance_json=row.provenance_json,
                            d.source_system=$source
                    """, rows=list(dish_rows.values()), source=self.SOURCE)

                if recipe_rows:
                    run("""
                        UNWIND $rows AS row
                        MERGE (r:Recipe {recipe_id: row.recipe_id})
                        SET r.name=row.name, r.servings=row.servings,
                            r.instructions=row.instructions,
                            r.source_system=$source, r.is_public=true
                    """, rows=list(recipe_rows.values()), source=self.SOURCE)

                if ingredient_rows:
                    run("""
                        UNWIND $rows AS row
                        MATCH (r:Recipe {recipe_id: row.recipe_id})
                        MERGE (i:Ingredient {normalized_name: row.normalized_name})
                        SET i.name=row.name, i.mapping_status=row.mapping_status,
                            i.quantity_status=row.quantity_status
                        MERGE (r)-[u:USES_INGREDIENT]->(i)
                        SET u.quantity=row.quantity, u.unit=row.unit,
                            u.source_system=$source
                    """, rows=ingredient_rows, source=self.SOURCE)

                if ingredient_food_rows:
                    run("""
                        UNWIND $rows AS row
                        MATCH (i:Ingredient {normalized_name: row.normalized_name})
                        MATCH (f:Food {food_id: row.food_id})
                        MERGE (i)-[rel:RESOLVES_TO]->(f)
                        SET rel.source_system=$source
                    """, rows=ingredient_food_rows, source=self.SOURCE)

                if dish_recipe_rows:
                    run("""
                        UNWIND $rows AS row
                        MATCH (d:Dish {dish_id: row.dish_id})
                        MATCH (r:Recipe {recipe_id: row.recipe_id})
                        MERGE (d)-[rel:HAS_RECIPE]->(r)
                        SET rel.source=row.source, rel.provenance_json=row.provenance_json,
                            rel.source_system=$source
                    """, rows=dish_recipe_rows, source=self.SOURCE)

                # Sanitize every previously synchronized recipe absent from
                # the current public SQL snapshot, even if it has no relationships.
                run("""
                    MATCH (r:Recipe)
                    WHERE r.source_system=$source
                      AND NOT r.recipe_id IN $recipe_ids
                    SET r.is_public=false
                    REMOVE r.name, r.servings, r.instructions
                """, source=self.SOURCE, recipe_ids=recipe_ids)

                # Global reconciliation is restricted to relationships owned by
                # this synchronizer. Empty snapshots are handled by empty pair lists.
                run("""
                    MATCH (d:Dish)-[rel:HAS_RECIPE]->(r:Recipe)
                    WHERE rel.source_system=$source
                      AND NOT any(p IN $pairs
                        WHERE p.dish_id=d.dish_id AND p.recipe_id=r.recipe_id)
                    DELETE rel
                """, source=self.SOURCE, pairs=dr_pairs)

                run("""
                    MATCH (r:Recipe)-[rel:USES_INGREDIENT]->(i:Ingredient)
                    WHERE rel.source_system=$source
                      AND NOT any(p IN $pairs
                        WHERE p.recipe_id=r.recipe_id
                          AND p.normalized_name=i.normalized_name)
                    DELETE rel
                """, source=self.SOURCE, pairs=ri_pairs)

                run("""
                    MATCH (i:Ingredient)-[rel:RESOLVES_TO]->(f:Food)
                    WHERE rel.source_system=$source
                      AND NOT any(p IN $pairs
                        WHERE p.normalized_name=i.normalized_name
                          AND p.food_id=f.food_id)
                    DELETE rel
                """, source=self.SOURCE, pairs=mapping_pairs)

                run("""
                    MATCH (f:Food)-[rel:HAS_NUTRIENT]->(n:Nutrient)
                    WHERE rel.source_system=$source
                      AND NOT any(p IN $pairs
                        WHERE p.food_id=f.food_id AND p.key=n.key)
                    DELETE rel
                """, source=self.SOURCE, pairs=nutrient_pairs)

                tx.commit()
            except Exception:
                tx.rollback()
                raise

        return snapshot_counts


knowledge_graph = KnowledgeGraph()

