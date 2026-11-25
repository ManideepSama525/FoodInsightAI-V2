from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import food_fraud as fraud_route
from backend.app.core.auth import get_current_user
from backend.app.main import app


@pytest.fixture
def toxifruit_api(monkeypatch):
    state = {"calls": []}

    async def fake_validate(upload, max_bytes):
        return SimpleNamespace(
            content=b"test-image",
            media_type="image/jpeg",
            extension=".jpg",
        )

    async def fake_screen(**kwargs):
        state["calls"].append(kwargs)
        return {
            "predicted_class": "Fresh Apple",
            "category": "fruit",
            "fruit": "Apple",
            "vegetable": None,
            "condition": "fresh_control",
            "confidence": 0.97,
            "probabilities": {
                "Fresh Apple": 0.97,
                "Formalin-treated Apple": 0.03,
                "Fresh Banana": 0.0,
                "Formalin-treated Banana": 0.0,
                "Fresh Malta": 0.0,
                "Formalin-treated Malta": 0.0,
                "Fresh Mango": 0.0,
                "Formalin-treated Mango": 0.0,
                "Defective Potato": 0.0,
                "Defective Bitter Gourd": 0.0,
                "Defective Brinjal": 0.0,
                "Defective Capsicum": 0.0,
                "Defective Onion": 0.0,
                "Defective Pointed Gourd": 0.0,
                "Defective Tomato": 0.0,
                "Fresh Bitter Gourd": 0.0,
                "Fresh Brinjal": 0.0,
                "Fresh Capsicum": 0.0,
                "Fresh Onion": 0.0,
                "Fresh Pointed Gourd": 0.0,
                "Fresh Potato": 0.0,
                "Fresh Tomato": 0.0,
            },
            "model": "EfficientNet-B0",
            "model_version": "toxifruit-vegetable-grouped-letterbox-v2",
            "interpretation": "Visual screening only. Not chemical confirmation.",
        }

    monkeypatch.setattr(fraud_route, "validate_image_upload", fake_validate)
    monkeypatch.setattr(fraud_route, "screen_produce", fake_screen)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)

    client = TestClient(app)

    yield SimpleNamespace(
        client=client,
        state=state,
        path="/api/v1/food-fraud/produce/visual-screening",
    )

    app.dependency_overrides.pop(get_current_user, None)


def post_screen(harness):
    return harness.client.post(
        harness.path,
        files={
            "file": (
                "apple.jpg",
                b"placeholder",
                "image/jpeg",
            )
        },
    )


def test_toxifruit_screening_returns_valid_result(toxifruit_api):
    response = post_screen(toxifruit_api)

    assert response.status_code == 200
    body = response.json()

    assert body["predicted_class"] == "Fresh Apple"
    assert body["fruit"] == "Apple"
    assert body["condition"] == "fresh_control"
    assert body["confidence"] == 0.97
    assert body["model_version"] == "toxifruit-vegetable-grouped-letterbox-v2"
    assert len(body["probabilities"]) == 22

    assert len(toxifruit_api.state["calls"]) == 1
    assert toxifruit_api.state["calls"][0]["image_content"] == b"test-image"


def test_toxifruit_service_unavailable_returns_503(toxifruit_api, monkeypatch):
    async def unavailable(**kwargs):
        raise fraud_route.ToxiFruitServiceUnavailable(
            "ToxiFruit visual screening service is unavailable."
        )

    monkeypatch.setattr(fraud_route, "screen_produce", unavailable)
    response = post_screen(toxifruit_api)

    assert response.status_code == 503


def test_toxifruit_upstream_error_is_preserved(toxifruit_api, monkeypatch):
    async def rejected(**kwargs):
        raise fraud_route.ToxiFruitServiceError(
            422,
            "Unsupported image.",
        )

    monkeypatch.setattr(fraud_route, "screen_produce", rejected)
    response = post_screen(toxifruit_api)

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported image."


def test_toxifruit_validation_error_returns_422(toxifruit_api, monkeypatch):
    async def invalid(upload, max_bytes):
        raise fraud_route.ImageValidationError("Invalid image.")

    monkeypatch.setattr(fraud_route, "validate_image_upload", invalid)
    response = post_screen(toxifruit_api)

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid image."
    assert toxifruit_api.state["calls"] == []

def test_toxifruit_vegetable_screening_returns_valid_result(toxifruit_api, monkeypatch):
    async def fake_vegetable_screen(**kwargs):
        return {
            "predicted_class": "Fresh Capsicum",
            "category": "vegetable",
            "fruit": None,
            "vegetable": "Fresh Capsicum",
            "condition": None,
            "confidence": 0.91,
            "probabilities": {
                "Fresh Capsicum": 0.91,
                "Defective Capsicum": 0.09,
            },
            "model": "EfficientNet-B0",
            "model_version": "toxifruit-vegetable-grouped-letterbox-v2",
            "interpretation": "Visual screening only. Not chemical confirmation.",
        }

    monkeypatch.setattr(fraud_route, "screen_produce", fake_vegetable_screen)
    response = post_screen(toxifruit_api)

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "vegetable"
    assert body["vegetable"] == "Fresh Capsicum"
    assert body["fruit"] is None
    assert body["condition"] is None
