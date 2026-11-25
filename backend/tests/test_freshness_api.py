from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import freshness as freshness_route
from backend.app.main import app


@pytest.fixture
def freshness_api(monkeypatch):
    state = {"calls": []}

    async def fake_validate(upload, max_bytes):
        return SimpleNamespace(
            content=b"test-image",
            media_type="image/jpeg",
            extension=".jpg",
        )

    async def fake_predict(**kwargs):
        state["calls"].append(kwargs)

        return {
            "model_version": "freshness-v1",
            "category": kwargs["category"],
            "predicted_label": "Fresh",
            "confidence": 0.96,
            "probabilities": {
                "Fresh": 0.96,
                "Rotten": 0.04,
            },
            "device": "cpu",
            "safety_notice": "Image-based estimate only.",
        }

    monkeypatch.setattr(
        freshness_route,
        "validate_image_upload",
        fake_validate,
    )
    monkeypatch.setattr(
        freshness_route,
        "predict_freshness",
        fake_predict,
    )

    client = TestClient(app)

    yield SimpleNamespace(
        client=client,
        state=state,
        path="/api/v1/freshness/predict",
    )


def post_freshness(harness, category="apple"):
    return harness.client.post(
        harness.path,
        data={"category": category},
        files={
            "file": (
                "apple.jpg",
                b"placeholder",
                "image/jpeg",
            )
        },
    )


def test_freshness_prediction_returns_valid_response(freshness_api):
    response = post_freshness(freshness_api)

    assert response.status_code == 200

    body = response.json()

    assert body["model_version"] == "freshness-v1"
    assert body["category"] == "apple"
    assert body["predicted_label"] == "Fresh"
    assert body["confidence"] == 0.96
    assert body["probabilities"]["Fresh"] == 0.96

    assert len(freshness_api.state["calls"]) == 1

    call = freshness_api.state["calls"][0]
    assert call["category"] == "apple"
    assert call["image_content"] == b"test-image"


def test_freshness_category_is_normalized(freshness_api):
    response = post_freshness(freshness_api, "  APPLE  ")

    assert response.status_code == 200
    assert response.json()["category"] == "apple"


def test_empty_freshness_category_is_rejected(freshness_api):
    response = post_freshness(freshness_api, "   ")

    assert response.status_code == 422
    assert freshness_api.state["calls"] == []


def test_freshness_service_unavailable_returns_503(
    freshness_api,
    monkeypatch,
):
    async def unavailable(**kwargs):
        raise freshness_route.FreshnessServiceUnavailable(
            "Freshness inference service is unavailable."
        )

    monkeypatch.setattr(
        freshness_route,
        "predict_freshness",
        unavailable,
    )

    response = post_freshness(freshness_api)

    assert response.status_code == 503


def test_freshness_upstream_category_error_is_preserved(
    freshness_api,
    monkeypatch,
):
    async def unsupported(**kwargs):
        raise freshness_route.FreshnessServiceError(
            422,
            "Unsupported freshness category.",
        )

    monkeypatch.setattr(
        freshness_route,
        "predict_freshness",
        unsupported,
    )

    response = post_freshness(freshness_api)

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported freshness category."
