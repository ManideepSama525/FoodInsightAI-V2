$ErrorActionPreference = "Stop"
$root = (Get-Location).Path
if (-not (Test-Path ".\docker-compose.yml") -or -not (Test-Path ".\backend\app\main.py")) {
    throw "Run this script from C:\Users\manid\FoodInsightAI-V2"
}

# Preserve the current .env and add Neo4j credentials only when absent.
$envPath = ".\.env"
$envText = if (Test-Path $envPath) { Get-Content $envPath -Raw } else { "" }
if ($envText -notmatch '(?m)^NEO4J_PASSWORD=') {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $neoPassword = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','A').Replace('/','B')
    $rng.Dispose()
    Add-Content -Path $envPath -Value "`r`n# Neo4j graph database`r`nNEO4J_PASSWORD=$neoPassword`r`nNEO4J_USERNAME=neo4j`r`nNEO4J_URI=bolt://neo4j:7687`r`nNEO4J_DATABASE=neo4j`r`nKNOWLEDGE_GRAPH_ENABLED=true" -Encoding UTF8
}
if ($envText -notmatch '(?m)^NEO4J_USERNAME=') { Add-Content $envPath "`r`nNEO4J_USERNAME=neo4j" -Encoding UTF8 }
if ($envText -notmatch '(?m)^NEO4J_URI=') { Add-Content $envPath "`r`nNEO4J_URI=bolt://neo4j:7687" -Encoding UTF8 }
if ($envText -notmatch '(?m)^NEO4J_DATABASE=') { Add-Content $envPath "`r`nNEO4J_DATABASE=neo4j" -Encoding UTF8 }
if ($envText -notmatch '(?m)^KNOWLEDGE_GRAPH_ENABLED=') { Add-Content $envPath "`r`nKNOWLEDGE_GRAPH_ENABLED=true" -Encoding UTF8 }

# Add the official Neo4j Python driver to the backend dependencies.
$py = Get-Content ".\pyproject.toml" -Raw
if ($py -notmatch '"neo4j') {
    $py = $py.Replace('"PyJWT>=2.9,<3.0"', '"PyJWT>=2.9,<3.0", "neo4j>=5.25,<7.0"')
    Set-Content ".\pyproject.toml" $py -Encoding UTF8
}

# Add graph settings without changing existing settings.
$configPath = ".\backend\app\core\config.py"
$config = Get-Content $configPath -Raw
if ($config -notmatch 'neo4j_uri:') {
    $config = $config.Replace('    access_token_expire_minutes: int = 10080', @'
    access_token_expire_minutes: int = 10080
    knowledge_graph_enabled: bool = False
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
'@.TrimEnd())
    Set-Content $configPath $config -Encoding UTF8
}

# Graph service: optional connection, stable relational IDs, idempotent MERGE-based ETL.
New-Item -ItemType Directory -Force ".\backend\app\services" | Out-Null
@'
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
            return bool(self._driver.verify_connectivity())
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
'@ | Set-Content ".\backend\app\services\knowledge_graph.py" -Encoding UTF8

@'
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.knowledge_graph import knowledge_graph

router = APIRouter(prefix="/knowledge-graph", tags=["food knowledge graph"])


@router.get("/status")
def graph_status() -> dict[str, object]:
    return {
        "enabled": knowledge_graph.enabled,
        "connected": knowledge_graph.verify() if knowledge_graph.enabled else False,
        "database": "neo4j",
    }


@router.post("/sync")
def synchronize_graph(db: Session = Depends(get_db)) -> dict[str, int]:
    try:
        return knowledge_graph.sync(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Knowledge graph synchronization failed") from exc


@router.get("/foods/{food_id}")
def food_neighborhood(food_id: int) -> dict:
    try:
        result = knowledge_graph.food_neighborhood(food_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Food not found in knowledge graph")
    return result
'@ | Set-Content ".\backend\app\api\routes\knowledge_graph.py" -Encoding UTF8

$routerPath = ".\backend\app\api\router.py"
$router = Get-Content $routerPath -Raw
if ($router -notmatch 'knowledge_graph_router') {
    $router = $router.Replace('from backend.app.api.routes.health import router as health_router', 'from backend.app.api.routes.health import router as health_router' + "`r`n" + 'from backend.app.api.routes.knowledge_graph import router as knowledge_graph_router')
    $router += "`r`napi_router.include_router(knowledge_graph_router)`r`n"
    Set-Content $routerPath $router -Encoding UTF8
}

# Add Neo4j service and isolated persistent volume. Existing SQLite volume is retained.
$composePath = ".\docker-compose.yml"
$compose = Get-Content $composePath -Raw
if ($compose -notmatch '(?m)^\s+neo4j:') {
    $compose = $compose.Replace('services:' + "`r`n", @'
services:
  neo4j:
    image: neo4j:5.26-community
    environment:
      NEO4J_AUTH: ${NEO4J_USERNAME:-neo4j}/${NEO4J_PASSWORD:?Set NEO4J_PASSWORD in .env}
      NEO4J_server_memory_heap_initial__size: 256m
      NEO4J_server_memory_heap_max__size: 512m
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - foodinsightai_neo4j_data:/data
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u $${NEO4J_AUTH%%/*} -p $${NEO4J_AUTH#*/} 'RETURN 1' >/dev/null 2>&1"]
      interval: 15s
      timeout: 10s
      retries: 10
      start_period: 30s
    restart: unless-stopped

'@)
    $compose = $compose.Replace('      RECOGNITION_MODEL_VERSION: food101-efficientnetv2s-v1', @'
      RECOGNITION_MODEL_VERSION: food101-efficientnetv2s-v1
      KNOWLEDGE_GRAPH_ENABLED: ${KNOWLEDGE_GRAPH_ENABLED:-true}
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USERNAME: ${NEO4J_USERNAME:-neo4j}
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      NEO4J_DATABASE: ${NEO4J_DATABASE:-neo4j}
'@.TrimEnd())
    $compose = $compose.Replace('    restart: unless-stopped' + "`r`n" + "`r`n  frontend:", @'
    depends_on:
      neo4j:
        condition: service_healthy
    restart: unless-stopped

  frontend:
'@)
    $compose = $compose.Replace('  foodinsightai_data:' + "`r`n", '  foodinsightai_data:' + "`r`n" + '  foodinsightai_neo4j_data:' + "`r`n")
    Set-Content $composePath $compose -Encoding UTF8
}

# Keep example environment documentation aligned without copying real credentials.
$examplePath = ".\.env.example"
$example = Get-Content $examplePath -Raw
if ($example -notmatch '(?m)^NEO4J_URI=') {
    Add-Content $examplePath "`r`n# Optional Neo4j knowledge graph`r`nKNOWLEDGE_GRAPH_ENABLED=true`r`nNEO4J_URI=bolt://neo4j:7687`r`nNEO4J_USERNAME=neo4j`r`nNEO4J_PASSWORD=replace-with-a-long-random-secret`r`nNEO4J_DATABASE=neo4j" -Encoding UTF8
}

Write-Host "`nKnowledge Graph files and configuration created."
Write-Host "Existing SQLite volume and dataset files were not modified."
Write-Host "Next: rebuild and start services, then run the graph synchronization endpoint."
