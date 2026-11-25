from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.services.knowledge_graph import (
    KnowledgeGraph,
    _build_unambiguous_ingredient_food_rows,
    _normalize_ingredient_name,
    knowledge_graph,
)


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
        self.committed = False
        self.rolled_back = False

    def run(self, query, **parameters):
        self.statements.append((query, parameters))
        return FakeGraphResult()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeGraphSession:
    def __init__(self, statements, neighborhood_record=None):
        self.statements = statements
        self.neighborhood_record = neighborhood_record
        self.transaction = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def run(self, query, **parameters):
        self.statements.append((query, parameters))
        if "MATCH (f:Food" in query:
            return FakeGraphResult(self.neighborhood_record)
        return FakeGraphResult()

    def begin_transaction(self):
        self.transaction = FakeGraphTransaction(self.statements)
        return self.transaction


class FakeGraphDriver:
    def __init__(self, neighborhood_record=None):
        self.statements = []
        self.neighborhood_record = neighborhood_record
        self.sessions = []

    def session(self, **kwargs):
        session = FakeGraphSession(self.statements, self.neighborhood_record)
        self.sessions.append(session)
        return session


class FakeScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def unique(self):
        return self


class FakeDatabase:
    """Return SQL rows in the order used by KnowledgeGraph.sync()."""

    def __init__(self, foods, associations=None, dishes=None):
        associations = associations or []
        if dishes is None:
            # The graph sync loads canonical active Dishes independently
            # from public Dish-Recipe associations.
            unique_dishes = {}
            for association in associations:
                dish = getattr(association, "dish", None)
                if dish is not None:
                    unique_dishes[dish.id] = dish
            dishes = list(unique_dishes.values())

        self.results = [
            FakeScalarResult(foods),
            FakeScalarResult(dishes),
            FakeScalarResult(associations),
        ]
        self.statements = []

    def scalars(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected additional SQL scalars() call")
        return self.results.pop(0)


def make_food(food_id=10, nutrients=None):
    return SimpleNamespace(
        id=food_id,
        name="Cooked rice",
        normalized_name="cooked rice",
        category="Grains",
        source="test",
        external_id=None,
        source_url=None,
        description=None,
        nutrients=nutrients or [],
    )


def make_association(
    recipe_id=20,
    ingredient_rows=None,
    dish_id=30,
    source="curated",
    provenance=None,
):
    dish = SimpleNamespace(
        id=dish_id,
        name="Rice dish",
        normalized_name="rice dish",
        category="main",
        source="test_catalog",
        provenance={"reviewed": True},
        is_active=True,
    )
    recipe = SimpleNamespace(
        id=recipe_id,
        name=f"Rice recipe {recipe_id}",
        servings=2,
        instructions="Cook rice",
        ingredients=ingredient_rows or [],
        user_id=None,
    )
    return SimpleNamespace(
        id=recipe_id + 100,
        dish_id=dish_id,
        recipe_id=recipe_id,
        dish=dish,
        recipe=recipe,
        source=source,
        provenance=provenance or {"catalog": "reviewed"},
        is_active=True,
    )


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
        "recipes": [],
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
        "dishes_synced": 0,
        "recipes_synced": 0,
        "dish_recipe_relationships_synced": 0,
        "ingredient_mentions_synced": 0,
        "ingredient_food_relationships_synced": 0,
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


def test_food_neighborhood_returns_graph_record_and_measurement_provenance(monkeypatch):
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
    record = {"food": expected_food, "nutrients": expected_nutrients}

    graph = KnowledgeGraph()
    driver = FakeGraphDriver(neighborhood_record=record)
    monkeypatch.setattr(graph, "_driver", driver)

    result = graph.food_neighborhood(10)

    assert result == {
        "food": expected_food,
        "nutrients": [expected_nutrients[0]],
        "recipes": [],
    }
    assert driver.statements[0][1]["food_id"] == 10
    assert "OPTIONAL MATCH" in driver.statements[0][0]


def test_food_neighborhood_returns_none_for_missing_food(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver(neighborhood_record=None)
    monkeypatch.setattr(graph, "_driver", driver)

    assert graph.food_neighborhood(999999) is None


def test_sync_preserves_food_nutrient_dish_recipe_and_ingredient_data(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    food = make_food(nutrients=[
        SimpleNamespace(
            nutrient_key="protein", display_name="Protein", amount=2.5,
            unit="g", basis_g=100, source="test", source_nutrient_id="N1",
            derivation_code="NC",
            derivation_description="Calculated",
            derivation_source_description="Calculated from component nutrients",
        ),
        SimpleNamespace(
            nutrient_key="vitamin_c", display_name="Vitamin C", amount=None,
            unit="mg", basis_g=100, source="test", source_nutrient_id="N2",
        ),
    ])
    ingredient = SimpleNamespace(
        food_id=10,
        ingredient_name="Cooked rice",
        quantity=200,
        unit="g",
        mapping_status="approved_alias",
        quantity_status="provided",
    )
    association = make_association(ingredient_rows=[ingredient])

    result = graph.sync(FakeDatabase([food], [association]))

    assert result == {
        "foods_synced": 1,
        "nutrient_relationships_synced": 1,
        "dishes_synced": 1,
        "recipes_synced": 1,
        "dish_recipe_relationships_synced": 1,
        "ingredient_mentions_synced": 1,
        "ingredient_food_relationships_synced": 1,
    }

    writes = [
        (query, params)
        for query, params in driver.statements
        if "UNWIND $rows AS row" in query
    ]
    assert len(writes) == 7

    food_query, food_params = writes[0]
    assert "MERGE (f:Food {food_id: row.food_id})" in food_query
    assert food_params["rows"][0]["food_id"] == 10

    nutrient_query, nutrient_params = writes[1]
    assert "MERGE (n:Nutrient {key: row.key})" in nutrient_query
    assert "MERGE (f)-[r:HAS_NUTRIENT]->(n)" in nutrient_query
    assert len(nutrient_params["rows"]) == 1
    assert nutrient_params["rows"][0]["amount"] == 2.5
    assert nutrient_params["rows"][0]["basis_g"] == 100.0
    assert nutrient_params["rows"][0]["source_nutrient_id"] == "N1"
    assert nutrient_params["rows"][0]["derivation_code"] == "NC"
    assert nutrient_params["rows"][0]["derivation_description"] == "Calculated"
    assert (
        nutrient_params["rows"][0]["derivation_source_description"]
        == "Calculated from component nutrients"
    )

    dish_query, dish_params = writes[2]
    assert "MERGE (d:Dish {dish_id: row.dish_id})" in dish_query
    assert dish_params["rows"][0]["dish_id"] == 30

    recipe_query, recipe_params = writes[3]
    assert "MERGE (r:Recipe {recipe_id: row.recipe_id})" in recipe_query
    assert recipe_params["rows"][0]["recipe_id"] == 20

    ingredient_query, ingredient_params = writes[4]
    assert "MERGE (r)-[u:USES_INGREDIENT]->(i)" in ingredient_query
    assert ingredient_params["rows"][0]["normalized_name"] == "cooked rice"

    mapping_query, mapping_params = writes[5]
    assert "MERGE (i)-[rel:RESOLVES_TO]->(f)" in mapping_query
    assert mapping_params["rows"] == [
        {"normalized_name": "cooked rice", "food_id": 10}
    ]

    association_write = next(
        params for query, params in driver.statements
        if "MERGE (d)-[rel:HAS_RECIPE]->(r)" in query
    )
    assert association_write["rows"][0]["provenance_json"] == '{"catalog": "reviewed"}'


def test_sync_requires_public_active_dish_recipe_associations(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    association = make_association()
    db = FakeDatabase([make_food()], [association])
    result = graph.sync(db)

    assert result["dish_recipe_relationships_synced"] == 1
    sql = str(db.statements[2]).lower()
    assert "recipes.user_id is null" in sql
    assert "dish_recipes.is_active" in sql


def test_sync_rejects_empty_canonical_food_snapshot_before_graph_access(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    with pytest.raises(RuntimeError, match="canonical Food snapshot is empty"):
        graph.sync(FakeDatabase([], []))

    assert driver.statements == []


def test_sync_dry_run_builds_snapshot_without_neo4j_access(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    result = graph.sync(FakeDatabase([make_food()], []), dry_run=True)

    assert result["dry_run"] is True
    assert result["foods_synced"] == 1
    assert result["nutrient_relationships_synced"] == 0
    assert driver.statements == []


def test_sync_uses_merge_and_single_transaction_for_idempotent_writes(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)
    food = make_food()

    graph.sync(FakeDatabase([food], []))
    graph.sync(FakeDatabase([food], []))

    merge_queries = [
        query for query, _ in driver.statements
        if "UNWIND $rows AS row" in query
    ]
    assert merge_queries
    assert all("MERGE" in query for query in merge_queries)
    data_sessions = [
        session for session in driver.sessions if session.transaction is not None
    ]
    assert len(data_sessions) == 2
    assert all(session.transaction.committed for session in data_sessions)


def test_sync_reconciles_owned_relationships_without_deleting_nodes(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    graph.sync(FakeDatabase([make_food()], []))
    statements = [query for query, _ in driver.statements]

    assert any("DELETE rel" in query and "HAS_NUTRIENT" in query for query in statements)
    assert any("DELETE rel" in query and "USES_INGREDIENT" in query for query in statements)
    assert any("DELETE rel" in query and "RESOLVES_TO" in query for query in statements)
    assert any("DELETE rel" in query and "HAS_RECIPE" in query for query in statements)
    assert not any("DETACH DELETE" in query for query in statements)
    assert not any("DELETE f" in query or "DELETE n" in query for query in statements)


def test_sync_preserves_shared_unambiguous_ingredient_mapping(monkeypatch):
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    monkeypatch.setattr(graph, "_driver", driver)

    item_a = SimpleNamespace(
        food_id=10, ingredient_name="Cooked Rice", quantity=100, unit="g",
        mapping_status="approved_alias", quantity_status="provided",
    )
    item_b = SimpleNamespace(
        food_id=10, ingredient_name=" cooked rice ", quantity=150, unit="g",
        mapping_status="exact_name", quantity_status="provided",
    )
    associations = [
        make_association(20, [item_a], dish_id=30),
        make_association(21, [item_b], dish_id=30),
    ]

    result = graph.sync(FakeDatabase([make_food()], associations))

    assert result["recipes_synced"] == 2
    mapping_write = next(
        params for query, params in driver.statements
        if "MERGE (i)-[rel:RESOLVES_TO]->(f)" in query
    )
    assert mapping_write["rows"] == [
        {"normalized_name": "cooked rice", "food_id": 10}
    ]


def test_conflicting_ingredient_mappings_are_not_synced():
    rows = _build_unambiguous_ingredient_food_rows([
        ("cooked rice", 10),
        ("cooked rice", 11),
    ])
    assert rows == []


def test_ingredient_name_normalization_is_unicode_and_whitespace_safe():
    assert _normalize_ingredient_name("  CAFÉ   rice ") == "café rice"
    assert _normalize_ingredient_name("cafe\u0301 rice") == "café rice"


def test_sync_queries_only_shared_recipes():
    graph = KnowledgeGraph()
    driver = FakeGraphDriver()
    graph._driver = driver
    db = FakeDatabase([make_food()], [])

    graph.sync(db)

    assert len(db.statements) == 3
    association_query = str(db.statements[2]).lower()
    assert "recipes.user_id is null" in association_query


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
