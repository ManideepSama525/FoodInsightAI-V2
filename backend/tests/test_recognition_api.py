from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import recognition as recognition_route
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.core.config import get_settings


class FakeProvider:
    def __init__(self, result):
        self.result = result

    def predict(self, content):
        assert content == b"test-image"
        return self.result


@pytest.fixture
def recognition_api(monkeypatch):
    db_sentinel = object()

    def override_get_db():
        yield db_sentinel

    app.dependency_overrides[get_db] = override_get_db

    async def fake_validate_image_upload(upload, max_bytes):
        assert max_bytes > 0
        return SimpleNamespace(content=b"test-image")

    monkeypatch.setattr(
        recognition_route,
        "validate_image_upload",
        fake_validate_image_upload,
    )

    state = {"dish_calls": [], "recipe_calls": []}

    def resolve_dish(db, label, model_source):
        assert db is db_sentinel
        state["dish_calls"].append((label, model_source))

        if label in ("pizza", "dosa"):
            return SimpleNamespace(id=7, name=label.title())

        return None

    recipe_payload = [{
        "recipe_id": 21,
        "recipe_name": "Test Recipe",
        "servings": 2,
        "source": "test-source",
        "source_url": "https://example.invalid/recipe",
        "source_attribution": "Test fixture",
        "association_source": "test",
        "association_provenance": {"fixture": True},
        "ingredients": [{
            "ingredient_name": "Rice",
            "food_id": None,
            "quantity": 1.0,
            "unit": "cup",
            "mapping_status": "unmapped",
            "quantity_status": "parsed",
        }],
    }]

    def get_recipes(db, dish_id):
        assert db is db_sentinel
        state["recipe_calls"].append(dish_id)
        return recipe_payload

    monkeypatch.setattr(
        recognition_route,
        "resolve_recognized_dish",
        resolve_dish,
    )
    monkeypatch.setattr(
        recognition_route,
        "get_public_dish_recipes",
        get_recipes,
    )

    def set_prediction(result, model="food101"):
        provider = FakeProvider(result)

        if model == "indian":
            monkeypatch.setattr(
                recognition_route,
                "get_indian_prediction_provider",
                lambda: provider,
            )
        else:
            monkeypatch.setattr(
                recognition_route,
                "get_prediction_provider",
                lambda: provider,
            )

    settings = get_settings()
    client = TestClient(app)
    path = f"{settings.api_v1_prefix}/recognition/predict"

    yield SimpleNamespace(
        client=client,
        path=path,
        state=state,
        set_prediction=set_prediction,
    )

    app.dependency_overrides.pop(get_db, None)


def make_result(
    predicted_food="pizza",
    needs_review=False,
    confidence=0.94,
    message=None,
):
    return SimpleNamespace(
        predicted_food=predicted_food,
        confidence=confidence,
        needs_review=needs_review,
        model_version="test-model-v1",
        top_predictions=[
            (predicted_food, confidence),
        ] if predicted_food else [],
        message=message,
    )


def post_prediction(harness, model="food101"):
    return harness.client.post(
        harness.path,
        params={"model": model},
        files={"file": ("test.jpg", b"placeholder", "image/jpeg")},
    )


def test_accepted_prediction_returns_analysis_routing_and_recipes(
    recognition_api,
):
    recognition_api.set_prediction(make_result())

    response = post_prediction(recognition_api)

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "recognized"
    assert body["predicted_food"] == "pizza"
    assert body["needs_review"] is False

    assert body["canonical_dish_id"] == 7
    assert body["canonical_dish_name"] == "Pizza"
    assert len(body["associated_recipes"]) == 1
    assert body["associated_recipes"][0]["recipe_name"] == "Test Recipe"
    assert body["associated_recipes"][0]["ingredients"][0]["ingredient_name"] == "Rice"

    assert body["canonical_food_id"] is None
    assert body["canonical_food_name"] is None

    routing = body["analysis_routing"]
    assert routing["status"] == "PARTIAL"
    assert routing["model_source"] == "food101"
    assert routing["food_label"] == "pizza"
    assert routing["freshness"] == "UNSUPPORTED"
    assert routing["nutrition"] == "LOOKUP_CANDIDATE"
    assert routing["recipe"] == "LOOKUP_CANDIDATE"
    assert routing["fraud"] == "NOT_VALIDATED"
    assert routing["requires_review"] is False

    assert recognition_api.state["dish_calls"] == [("pizza", "food101")]
    assert recognition_api.state["recipe_calls"] == [7]


def test_review_prediction_suppresses_dish_and_recipe_resolution(
    recognition_api,
):
    recognition_api.set_prediction(
        make_result(
            predicted_food="pizza",
            needs_review=True,
            confidence=0.42,
            message="Please review this prediction.",
        )
    )

    response = post_prediction(recognition_api)

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "needs_review"
    assert body["needs_review"] is True
    assert body["predicted_food"] == "pizza"
    assert body["canonical_dish_id"] is None
    assert body["canonical_dish_name"] is None
    assert body["associated_recipes"] == []
    assert body["message"] == "Please review this prediction."

    routing = body["analysis_routing"]
    assert routing["status"] == "REVIEW_REQUIRED"
    assert routing["freshness"] == "NOT_RUN"
    assert routing["nutrition"] == "NOT_RUN"
    assert routing["recipe"] == "NOT_RUN"
    assert routing["fraud"] == "NOT_RUN"
    assert routing["requires_review"] is True

    assert recognition_api.state["dish_calls"] == []
    assert recognition_api.state["recipe_calls"] == []


def test_valid_unknown_dish_alias_returns_prediction_without_recipes(
    recognition_api,
):
    recognition_api.set_prediction(make_result(predicted_food="waffles"))

    response = post_prediction(recognition_api)

    assert response.status_code == 200
    body = response.json()

    assert body["predicted_food"] == "waffles"
    assert body["needs_review"] is False
    assert body["canonical_dish_id"] is None
    assert body["canonical_dish_name"] is None
    assert body["associated_recipes"] == []

    assert body["analysis_routing"]["status"] == "PARTIAL"
    assert body["analysis_routing"]["food_label"] == "waffles"

    assert recognition_api.state["dish_calls"] == [("waffles", "food101")]
    assert recognition_api.state["recipe_calls"] == []


def test_indian_model_uses_indian_compatibility_mapping(recognition_api):
    recognition_api.set_prediction(
        make_result(predicted_food="dosa"),
        model="indian",
    )

    response = post_prediction(recognition_api, model="indian")

    assert response.status_code == 200
    body = response.json()

    assert body["canonical_dish_name"] == "Dosa"
    assert body["analysis_routing"]["model_source"] == "indian"
    assert body["analysis_routing"]["food_label"] == "dosa"
    assert body["analysis_routing"]["freshness"] == "UNSUPPORTED"

    assert recognition_api.state["dish_calls"] == [("dosa", "indian")]


def test_incompatible_model_output_returns_server_error(recognition_api):
    recognition_api.set_prediction(
        make_result(predicted_food="idli"),
    )

    response = post_prediction(recognition_api)

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Recognition output is not compatible with the analysis configuration."
    )
    assert recognition_api.state["dish_calls"] == []
    assert recognition_api.state["recipe_calls"] == []