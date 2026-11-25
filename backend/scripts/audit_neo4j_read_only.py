"""Read-only Neo4j inventory and synchronizer-ownership audit.

This script executes only MATCH/RETURN and SHOW CONSTRAINTS queries.
It does not create constraints, nodes, relationships, indexes, or properties.
"""
from collections import defaultdict

from neo4j import GraphDatabase

from backend.app.core.config import get_settings


SOURCE = "foodinsightai_sql"


def main() -> None:
    settings = get_settings()
    if not settings.knowledge_graph_enabled or not settings.neo4j_password:
        raise SystemExit(
            "Knowledge graph is disabled or credentials are not configured. "
            "No query was executed."
        )

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
        connection_timeout=5,
        max_connection_pool_size=2,
    )
    try:
        driver.verify_connectivity()
        with driver.session(database=settings.neo4j_database) as session:
            print("=" * 76)
            print("FOODINSIGHTAI NEO4J READ-ONLY AUDIT")
            print("No writes will be performed.")
            print("=" * 76)

            print("\n[1] NODE COUNTS BY LABEL")
            records = session.run("""
                MATCH (n)
                UNWIND labels(n) AS label
                RETURN label, count(*) AS node_count
                ORDER BY label
            """).data()
            for row in records:
                print(f'{row["label"]}: {row["node_count"]}')
            if not records:
                print("(no labeled nodes found)")

            print("\n[2] RELATIONSHIP COUNTS BY TYPE AND OWNERSHIP")
            records = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) AS relationship_type,
                       count(*) AS total,
                       sum(CASE WHEN r.source_system = $source THEN 1 ELSE 0 END) AS managed,
                       sum(CASE WHEN r.source_system IS NULL THEN 1 ELSE 0 END) AS untagged,
                       sum(CASE WHEN r.source_system IS NOT NULL
                                  AND r.source_system <> $source
                                THEN 1 ELSE 0 END) AS other_tagged
                ORDER BY relationship_type
            """, source=SOURCE).data()
            for row in records:
                print(
                    f'{row["relationship_type"]}: total={row["total"]}, '
                    f'managed={row["managed"]}, untagged={row["untagged"]}, '
                    f'other_tagged={row["other_tagged"]}'
                )
            if not records:
                print("(no relationships found)")

            print("\n[3] BASELINE FOOD / NUTRIENT COUNTS")
            records = session.run("""
                OPTIONAL MATCH (f:Food)
                WITH count(f) AS foods
                OPTIONAL MATCH (n:Nutrient)
                WITH foods, count(n) AS nutrients
                OPTIONAL MATCH (:Food)-[r:HAS_NUTRIENT]->(:Nutrient)
                RETURN foods, nutrients, count(r) AS has_nutrient_relationships,
                       sum(CASE WHEN r.source_system = $source THEN 1 ELSE 0 END)
                           AS managed_has_nutrient,
                       sum(CASE WHEN r.source_system IS NULL THEN 1 ELSE 0 END)
                           AS untagged_has_nutrient
            """, source=SOURCE).single()
            print(dict(records) if records else "(no result)")

            print("\n[4] RECIPE NODE PUBLICATION MARKERS")
            records = session.run("""
                MATCH (r:Recipe)
                RETURN count(r) AS all_recipe_nodes,
                       sum(CASE WHEN r.source_system = $source THEN 1 ELSE 0 END)
                           AS managed_recipe_nodes,
                       sum(CASE WHEN r.source_system = $source
                                  AND r.is_public = true THEN 1 ELSE 0 END)
                           AS managed_public,
                       sum(CASE WHEN r.source_system = $source
                                  AND r.is_public = false THEN 1 ELSE 0 END)
                           AS managed_non_public,
                       sum(CASE WHEN r.source_system = $source
                                  AND r.is_public IS NULL THEN 1 ELSE 0 END)
                           AS managed_missing_public_flag
            """, source=SOURCE).single()
            print(dict(records) if records else "(no recipe nodes found)")

            print("\n[5] SYNCHRONIZER-MANAGED RELATIONSHIP COUNTS")
            records = session.run("""
                MATCH ()-[r]->()
                WHERE r.source_system = $source
                RETURN type(r) AS relationship_type, count(*) AS count
                ORDER BY relationship_type
            """, source=SOURCE).data()
            for row in records:
                print(f'{row["relationship_type"]}: {row["count"]}')
            if not records:
                print("(no synchronizer-managed relationships found)")

            print("\n[6] AMBIGUOUS MANAGED INGREDIENT RESOLUTIONS")
            records = session.run("""
                MATCH (i:Ingredient)-[r:RESOLVES_TO]->(f:Food)
                WHERE r.source_system = $source
                WITH i, count(DISTINCT f.food_id) AS food_targets
                WHERE food_targets > 1
                RETURN count(*) AS ambiguous_ingredient_nodes,
                       sum(food_targets) AS total_food_targets
            """, source=SOURCE).single()
            print(dict(records) if records else "(no result)")

            print("\n[7] MANAGED RECIPE RELATIONSHIP INTEGRITY")
            records = session.run("""
                OPTIONAL MATCH (d:Dish)-[hr:HAS_RECIPE]->(r:Recipe)
                WHERE hr.source_system = $source
                WITH count(hr) AS managed_has_recipe,
                     sum(CASE WHEN d.dish_id IS NULL THEN 1 ELSE 0 END)
                         AS missing_dish_ids,
                     sum(CASE WHEN r.recipe_id IS NULL THEN 1 ELSE 0 END)
                         AS missing_recipe_ids
                OPTIONAL MATCH (r2:Recipe)-[ui:USES_INGREDIENT]->(i:Ingredient)
                WHERE ui.source_system = $source
                RETURN managed_has_recipe, missing_dish_ids, missing_recipe_ids,
                       count(ui) AS managed_uses_ingredient
            """, source=SOURCE).single()
            print(dict(records) if records else "(no result)")

            print("\n[8] CONSTRAINTS")
            try:
                records = session.run("SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties RETURN name, type, entityType, labelsOrTypes, properties ORDER BY name").data()
                for row in records:
                    print(dict(row))
                if not records:
                    print("(no constraints found)")
            except Exception as exc:
                print(f"Constraint listing unavailable: {type(exc).__name__}: {exc}")

            print("\n" + "=" * 76)
            print("AUDIT COMPLETE — READ ONLY")
            print("Compare Food/Nutrient counts with the previously recorded baseline:")
            print("395 Food nodes; 234 Nutrient nodes; 16,974 HAS_NUTRIENT relationships.")
            print("Counts may differ if legitimate data changes occurred since that audit.")
            print("=" * 76)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
