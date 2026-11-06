from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.config import get_settings
from backend.app.models.food import Food, FoodNutrient
from backend.app.models.recipe import Recipe

settings = get_settings()


class KnowledgeGraph:
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
        ]
        with self._driver.session(database=settings.neo4j_database) as session:
            for statement in statements:
                session.run(statement).consume()

    def sync(self, db: Session) -> dict[str, int]:
        if not self.enabled:
            raise RuntimeError("Knowledge graph is disabled or not configured")
        self.initialize()
        foods = db.scalars(select(Food).options(selectinload(Food.nutrients))).all()
        food_rows: list[dict[str, Any]] = []
        nutrient_rows: list[dict[str, Any]] = []
        for food in foods:
            food_rows.append({
                "food_id": food.id, "name": food.name,
                "normalized_name": food.normalized_name, "category": food.category,
                "source": food.source, "external_id": food.external_id,
                "source_url": food.source_url, "description": food.description,
            })
            for nutrient in food.nutrients:
                if nutrient.amount is None:
                    continue
                nutrient_rows.append({
                    "food_id": food.id, "key": nutrient.nutrient_key,
                    "name": nutrient.display_name, "amount": float(nutrient.amount),
                    "unit": nutrient.unit, "basis_g": float(nutrient.basis_g),
                    "source": nutrient.source,
                    "source_nutrient_id": nutrient.source_nutrient_id,
                })
        recipes = db.scalars(select(Recipe).options(selectinload(Recipe.ingredients))).all()
        recipe_rows: list[dict[str, Any]] = []
        for recipe in recipes:
            recipe_rows.append({
                "recipe_id": recipe.id, "name": recipe.name,
                "servings": recipe.servings, "instructions": recipe.instructions,
                "ingredients": [{
                    "food_id": item.food_id, "name": item.ingredient_name,
                    "quantity": float(item.quantity), "unit": item.unit,
                } for item in recipe.ingredients],
            })
        food_ids = [row["food_id"] for row in food_rows]
        recipe_ids = [row["recipe_id"] for row in recipe_rows]

        nutrient_pairs = [
            {"food_id": row["food_id"], "key": row["key"]}
            for row in nutrient_rows
        ]

        recipe_ingredient_pairs = [
            {
                "recipe_id": recipe["recipe_id"],
                "normalized_name": ingredient["name"].strip().lower(),
            }
            for recipe in recipe_rows
            for ingredient in recipe["ingredients"]
        ]

        ingredient_food_pairs = sorted({
            (ingredient["name"].strip().lower(), ingredient["food_id"])
            for recipe in recipe_rows
            for ingredient in recipe["ingredients"]
            if ingredient["food_id"] is not None
        })

        ingredient_food_pairs = [
            {"normalized_name": name, "food_id": food_id}
            for name, food_id in ingredient_food_pairs
        ]

        with self._driver.session(database=settings.neo4j_database) as session:
            session.execute_write(lambda tx: tx.run("""
                UNWIND $rows AS row
                MERGE (f:Food {food_id: row.food_id})
                SET f.name=row.name, f.normalized_name=row.normalized_name,
                    f.category=row.category, f.source=row.source,
                    f.external_id=row.external_id, f.source_url=row.source_url,
                    f.description=row.description
            """, rows=food_rows).consume())
            session.execute_write(lambda tx: tx.run("""
                UNWIND $rows AS row
                MATCH (f:Food {food_id: row.food_id})
                MERGE (n:Nutrient {key: row.key})
                SET n.name=row.name
                MERGE (f)-[r:HAS_NUTRIENT]->(n)
                SET r.amount=row.amount, r.unit=row.unit, r.basis_g=row.basis_g,
                    r.source=row.source, r.source_nutrient_id=row.source_nutrient_id
            """, rows=nutrient_rows).consume())
            session.execute_write(lambda tx: tx.run("""
                UNWIND $rows AS row
                MERGE (r:Recipe {recipe_id: row.recipe_id})
                SET r.name=row.name, r.servings=row.servings, r.instructions=row.instructions
                WITH r, row
                UNWIND row.ingredients AS ingredient
                MERGE (i:Ingredient {normalized_name: toLower(trim(ingredient.name))})
                SET i.name=ingredient.name
                MERGE (r)-[use:USES_INGREDIENT]->(i)
                SET use.quantity=ingredient.quantity, use.unit=ingredient.unit
                WITH i, ingredient
                OPTIONAL MATCH (f:Food {food_id: ingredient.food_id})
                FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END |
                    MERGE (i)-[:RESOLVES_TO]->(f))
            """, rows=recipe_rows).consume())

            # Remove nutrient relationships absent from the current food snapshot.
            session.execute_write(lambda tx: tx.run("""
                MATCH (f:Food)-[rel:HAS_NUTRIENT]->(n:Nutrient)
                WHERE f.food_id IN $food_ids
                  AND NOT any(pair IN $nutrient_pairs
                    WHERE pair.food_id = f.food_id AND pair.key = n.key)
                DELETE rel
            """, food_ids=food_ids, nutrient_pairs=nutrient_pairs).consume())

            # Remove ingredient mentions no longer present in each current recipe.
            session.execute_write(lambda tx: tx.run("""
                MATCH (r:Recipe)-[rel:USES_INGREDIENT]->(i:Ingredient)
                WHERE r.recipe_id IN $recipe_ids
                  AND NOT any(item IN $recipe_ingredient_pairs
                    WHERE item.recipe_id = r.recipe_id
                      AND item.normalized_name = i.normalized_name)
                DELETE rel
            """, recipe_ids=recipe_ids,
                 recipe_ingredient_pairs=recipe_ingredient_pairs).consume())

            # Reconcile shared ingredient-to-food mappings globally.
            session.execute_write(lambda tx: tx.run("""
                MATCH (i:Ingredient)-[rel:RESOLVES_TO]->(f:Food)
                WHERE NOT any(pair IN $ingredient_food_pairs
                    WHERE pair.normalized_name = i.normalized_name
                      AND pair.food_id = f.food_id)
                DELETE rel
            """, ingredient_food_pairs=ingredient_food_pairs).consume())

            # Remove graph recipes and foods deleted from the relational source.
            session.execute_write(lambda tx: tx.run("""
                MATCH (r:Recipe)
                WHERE NOT (r.recipe_id IN $recipe_ids)
                DETACH DELETE r
            """, recipe_ids=recipe_ids).consume())

            session.execute_write(lambda tx: tx.run("""
                MATCH (f:Food)
                WHERE NOT (f.food_id IN $food_ids)
                DETACH DELETE f
            """, food_ids=food_ids).consume())

            # Remove ingredients and nutrients that no longer have source relationships.
            session.execute_write(lambda tx: tx.run("""
                MATCH (i:Ingredient)
                WHERE NOT (i)<-[:USES_INGREDIENT]-()
                DETACH DELETE i
            """).consume())

            session.execute_write(lambda tx: tx.run("""
                MATCH (n:Nutrient)
                WHERE NOT (n)<-[:HAS_NUTRIENT]-()
                DETACH DELETE n
            """).consume())

        return {
            "foods_synced": len(food_rows),
            "nutrient_relationships_synced": len(nutrient_rows),
            "recipes_synced": len(recipe_rows),
            "ingredient_mentions_synced": sum(len(r["ingredients"]) for r in recipe_rows),
        }

    def food_neighborhood(self, food_id: int) -> dict[str, Any] | None:
        if not self.enabled:
            raise RuntimeError("Knowledge graph is disabled or not configured")
        with self._driver.session(database=settings.neo4j_database) as session:
            record = session.run("""
                MATCH (f:Food {food_id: $food_id})
                OPTIONAL MATCH (f)-[rel:HAS_NUTRIENT]->(n:Nutrient)
                RETURN f {.*} AS food,
                       collect(CASE WHEN n IS NULL THEN null ELSE
                         {name:n.name, key:n.key, amount:rel.amount,
                          unit:rel.unit, basis_g:rel.basis_g, source:rel.source} END)
                         AS nutrients
            """, food_id=food_id).single()
        if record is None:
            return None
        return {"food": record["food"], "nutrients": [x for x in record["nutrients"] if x]}


knowledge_graph = KnowledgeGraph()
