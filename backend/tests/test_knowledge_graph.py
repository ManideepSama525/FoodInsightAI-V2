from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.services.knowledge_graph import knowledge_graph


@pytest.fixture
def client():
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def authenticate():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, is_active=True
    )


def override_db():
    yield object()


def test_graph_status_rejects_unauthenticated_request(client):
    response = client.get("/api/v1/knowledge-graph/status")
    assert response.status_code == 401


def test_graph_sync_rejects_unauthenticated_request(client):
    response = client.post("/api/v1/knowledge-graph/sync")
    assert response.status_code == 401


def test_food_neighborhood_rejects_unauthenticated_request(client):
    response = client.get("/api/v1/knowledge-graph/foods/1")
    assert response.status_code == 401


def test_authenticated_graph_status(client, monkeypatch):
    authenticate()
    monkeypatch.setattr(
        type(knowledge_graph), "enabled", property(lambda self: True)
    )
    monkeypatch.setattr(knowledge_graph, "verify", lambda: True)

    response = client.get("/api/v1/knowledge-graph/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "connected": True,
        "database": "neo4j",
    }


def test_authenticated_food_neighborhood(client, monkeypatch):
    authenticate()
    expected = {
        "food": {"food_id": 1, "name": "Test rice"},
        "nutrients": [{"name": "Protein", "amount": 2.5, "unit": "g"}],
    }
    monkeypatch.setattr(
        knowledge_graph, "food_neighborhood", lambda food_id: expected
    )

    response = client.get("/api/v1/knowledge-graph/foods/1")

    assert response.status_code == 200
    assert response.json() == expected


def test_authenticated_sync(client, monkeypatch):
    authenticate()
    from backend.app.api.routes import knowledge_graph as graph_routes

    monkeypatch.setattr(
        graph_routes, "get_settings",
        lambda: SimpleNamespace(app_env="development"),
    )
    app.dependency_overrides[get_db] = override_db
    expected = {
        "foods_synced": 395,
        "nutrient_relationships_synced": 16974,
        "recipes_synced": 0,
        "ingredient_mentions_synced": 0,
    }
    monkeypatch.setattr(knowledge_graph, "sync", lambda db: expected)

    response = client.post("/api/v1/knowledge-graph/sync")

    assert response.status_code == 200
    assert response.json() == expected


def test_missing_food_returns_404(client, monkeypatch):
    authenticate()
    monkeypatch.setattr(
        knowledge_graph, "food_neighborhood", lambda food_id: None
    )

    response = client.get("/api/v1/knowledge-graph/foods/999999")

    assert response.status_code == 404
from backend.app.services.knowledge_graph import KnowledgeGraph


class FakeGraphResult:
    def __init__(self, record=None):
        self.record = record

    def consume(self):
        return None

    def single(self):
        return self.record


class FakeGraphTransaction:
    def __init__(self, statements):
        self.statements = statements

    def run(self, query, **parameters):
        self.statements.append((query, parameters))
        return FakeGraphResult()


class FakeGraphSession:
    def __init__(self, statements, neighborhood_record=None):
        self.statements = statements
        self.neighborhood_record = neighborhood_record

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def run(self, query, **parameters):
        self.statements.append((query, parameters))
        if "MATCH (f:Food" in query:
            return FakeGraphResult(self.neighborhood_record)
        return FakeGraphResult()

    def execute_write(self, callback):
        return callback(FakeGraphTransaction(self.statements))


class FakeGraphDriver:
    def __init__(self, neighborhood_record=None):
        self.statements = []
        self.neighborhood_record = neighborhood_record

    def session(self, **kwargs):
        return FakeGraphSession(self.statements, self.neighborhood_record)


class FakeScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeDatabase:
    def __init__(self, foods, recipes):
        self.results = [FakeScalarResult(foods), FakeScalarResult(recipes)]

    def scalars(self, statement):
        return self.results.pop(0)


def test_sync_preserves_food_nutrient_and_recipe_relationship_data(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    food = SimpleNamespace(
        id=10,
        name="Cooked rice",
        normalized_name="cooked rice",
        category="Grains",
        source="test",
        external_id=None,
        source_url=None,
        description=None,
        nutrients=[
            SimpleNamespace(
                nutrient_key="protein",
                display_name="Protein",
                amount=2.5,
                unit="g",
                basis_g=100,
                source="test",
                source_nutrient_id="N1",
            ),
            SimpleNamespace(
                nutrient_key="vitamin_c",
                display_name="Vitamin C",
                amount=None,
                unit="mg",
                basis_g=100,
                source="test",
                source_nutrient_id="N2",
            ),
        ],
    )
    recipe = SimpleNamespace(
        id=20,
        name="Rice bowl",
        servings=2,
        instructions="Cook rice",
        ingredients=[
            SimpleNamespace(
                food_id=10,
                ingredient_name="Cooked rice",
                quantity=200,
                unit="g",
            )
        ],
    )

    result = graph.sync(FakeDatabase([food], [recipe]))

    assert result == {
        "foods_synced": 1,
        "nutrient_relationships_synced": 1,
        "recipes_synced": 1,
        "ingredient_mentions_synced": 1,
    }

    writes = [
        (query, params)
        for query, params in driver.statements
        if "UNWIND $rows AS row" in query
    ]
    assert len(writes) == 3

    food_query, food_params = writes[0]
    assert "MERGE (f:Food {food_id: row.food_id})" in food_query
    assert food_params["rows"][0]["food_id"] == 10

    nutrient_query, nutrient_params = writes[1]
    assert "MERGE (n:Nutrient {key: row.key})" in nutrient_query
    assert "MERGE (f)-[r:HAS_NUTRIENT]->(n)" in nutrient_query
    assert len(nutrient_params["rows"]) == 1
    assert nutrient_params["rows"][0]["amount"] == 2.5

    recipe_query, recipe_params = writes[2]
    assert "MERGE (r:Recipe {recipe_id: row.recipe_id})" in recipe_query
    assert "MERGE (r)-[use:USES_INGREDIENT]->(i)" in recipe_query
    assert "MERGE (i)-[:RESOLVES_TO]->(f)" in recipe_query
    assert recipe_params["rows"][0]["ingredients"][0]["food_id"] == 10


def test_sync_uses_merge_for_idempotent_graph_writes(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    graph.sync(FakeDatabase([], []))
    graph.sync(FakeDatabase([], []))

    write_queries = [
        query
        for query, _ in driver.statements
        if "UNWIND $rows AS row" in query
    ]

    assert len(write_queries) == 6
    assert all("MERGE" in query for query in write_queries)


def test_food_neighborhood_returns_graph_record(monkeypatch):
    expected_food = {"food_id": 10, "name": "Cooked rice"}
    expected_nutrients = [
        {
            "name": "Protein",
            "key": "protein",
            "amount": 2.5,
            "unit": "g",
            "basis_g": 100,
            "source": "test",
        },
        None,
    ]
    record = {
        "food": expected_food,
        "nutrients": expected_nutrients,
    }

    graph = KnowledgeGraph()
    driver = FakeGraphDriver(neighborhood_record=record)
    monkeypatch.setattr(graph, "_driver", driver)

    result = graph.food_neighborhood(10)

    assert result == {
        "food": expected_food,
        "nutrients": [expected_nutrients[0]],
    }
    assert driver.statements[0][1]["food_id"] == 10


def test_food_neighborhood_returns_none_for_missing_food(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver(neighborhood_record=None)
    monkeypatch.setattr(graph, "_driver", driver)

    assert graph.food_neighborhood(999999) is None
def test_sync_reconciles_stale_relationships_and_deleted_nodes(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    graph.sync(FakeDatabase([], []))

    statements = [query for query, _ in driver.statements]

    assert any("DELETE rel" in query and "HAS_NUTRIENT" in query for query in statements)
    assert any("DELETE rel" in query and "USES_INGREDIENT" in query for query in statements)
    assert any("DELETE rel" in query and "RESOLVES_TO" in query for query in statements)
    assert any("DETACH DELETE r" in query for query in statements)
    assert any("DETACH DELETE f" in query for query in statements)
    assert any("DETACH DELETE i" in query for query in statements)
    assert any("DETACH DELETE n" in query for query in statements)


def test_sync_preserves_shared_ingredient_mappings_across_recipes(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    recipes = [
        SimpleNamespace(
            id=20,
            name="Rice bowl",
            servings=1,
            instructions=None,
            ingredients=[
                SimpleNamespace(
                    food_id=10,
                    ingredient_name="Cooked Rice",
                    quantity=100,
                    unit="g",
                )
            ],
        ),
        SimpleNamespace(
            id=21,
            name="Rice salad",
            servings=1,
            instructions=None,
            ingredients=[
                SimpleNamespace(
                    food_id=10,
                    ingredient_name=" cooked rice ",
                    quantity=150,
                    unit="g",
                )
            ],
        ),
    ]

    graph.sync(FakeDatabase([], recipes))

    mapping_writes = [
        parameters
        for query, parameters in driver.statements
        if "RESOLVES_TO" in query and "DELETE rel" in query
    ]

    assert len(mapping_writes) == 1
    assert mapping_writes[0]["ingredient_food_pairs"] == [
        {"normalized_name": "cooked rice", "food_id": 10}
    ]

def test_production_graph_sync_is_not_available(client, monkeypatch):
    authenticate()
    from backend.app.api.routes import knowledge_graph as graph_routes

    monkeypatch.setattr(
        graph_routes, "get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )
    monkeypatch.setattr(
        knowledge_graph, "sync",
        lambda db: pytest.fail("Graph sync must not execute in production"),
    )

    response = client.post("/api/v1/knowledge-graph/sync")

    assert response.status_code == 404
    assert response.json()["detail"] == "This endpoint is not available."


def test_readiness_reports_disabled_graph(client, monkeypatch):
    from backend.app import main

    monkeypatch.setattr(
        type(knowledge_graph), "enabled", property(lambda self: False)
    )

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
        "knowledge_graph": "disabled",
    }


def test_readiness_fails_when_enabled_graph_is_disconnected(client, monkeypatch):
    from backend.app import main

    monkeypatch.setattr(
        type(knowledge_graph), "enabled", property(lambda self: True)
    )
    monkeypatch.setattr(knowledge_graph, "verify", lambda: False)
    monkeypatch.setattr(main.settings, "knowledge_graph_enabled", True)

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 503
    assert response.json()["detail"] == "Knowledge graph is not ready."


def test_readiness_reports_connected_graph(client, monkeypatch):
    from backend.app import main

    monkeypatch.setattr(
        type(knowledge_graph), "enabled", property(lambda self: True)
    )
    monkeypatch.setattr(knowledge_graph, "verify", lambda: True)
    monkeypatch.setattr(main.settings, "knowledge_graph_enabled", True)

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 200
    assert response.json()["knowledge_graph"] == "connected"