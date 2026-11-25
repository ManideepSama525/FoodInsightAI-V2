from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import rag as rag_routes
from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.main import app


@pytest.fixture
def client():
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.clear()

    def override_db():
        yield object()

    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def authenticate():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        is_active=True,
    )


def sample_evidence():
    provenance = {
        "food_id": 10,
        "food_name": "Test cooked rice",
        "nutrient_key": "protein",
        "amount": 2.5,
        "unit": "g",
        "basis_g": 100,
        "source": "test",
    }

    return [
        {
            "source_type": "nutrient",
            "source_id": "nutrient-10-protein",
            "title": "Protein in Test cooked rice",
            "content": "Protein: 2.5 g per 100 g.",
            "provenance": provenance,
            "provenance_records": [provenance],
            "retrieval_sources": ["sql", "vector"],
            "rank_score": 0.03,
            "source_conflicts": [],
            "incomparable_measurements": [],
            "invalid_measurements": [],
        }
    ]


def test_rag_query_rejects_unauthenticated_request(client, monkeypatch):
    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        lambda *args, **kwargs: sample_evidence(),
    )

    response = client.post(
        "/api/v1/rag/query",
        json={"query": "protein in cooked rice"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": "x"},
        {"query": "protein", "top_k": 0},
        {"query": "protein", "top_k": 21},
        {"query": "protein", "claim": {"food_id": -1}},
    ],
)
def test_rag_query_rejects_invalid_input(client, payload):
    authenticate()

    response = client.post("/api/v1/rag/query", json=payload)

    assert response.status_code == 422


def test_rag_query_returns_evidence_and_citations(client, monkeypatch):
    authenticate()
    expected = sample_evidence()
    calls = []

    def fake_retrieve(db, query, top_k=8):
        calls.append((query, top_k))
        return expected

    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        fake_retrieve,
    )

    response = client.post(
        "/api/v1/rag/query",
        json={"query": "protein in cooked rice", "top_k": 5},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["query"] == "protein in cooked rice"
    assert body["retrieved_count"] == 1
    assert "2.5 g per 100 g" in body["answer"]
    assert body["citations"][0]["citation_id"] == (
        "nutrient:nutrient-10-protein"
    )
    assert body["citations"][0]["provenance"][0]["food_id"] == 10
    assert body["verification"] is None
    assert calls == [("protein in cooked rice", 5)]


def test_rag_query_verifies_nutrient_claim(client, monkeypatch):
    authenticate()

    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        lambda *args, **kwargs: sample_evidence(),
    )

    response = client.post(
        "/api/v1/rag/query",
        json={
            "query": "protein in cooked rice",
            "claim": {
                "food_id": 10,
                "nutrient_key": "protein",
                "amount": 2.5,
                "unit": "g",
                "basis_g": 100,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["verification"]["status"] == "supported"


def test_rag_query_reports_retrieval_unavailable(client, monkeypatch):
    authenticate()

    def fail_retrieval(*args, **kwargs):
        raise RuntimeError("Simulated retrieval failure")

    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        fail_retrieval,
    )

    response = client.post(
        "/api/v1/rag/query",
        json={"query": "protein in cooked rice"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Evidence retrieval is currently unavailable."
    )


def test_rag_query_rejects_invalid_bearer_token(client):
    response = client.post(
        "/api/v1/rag/query",
        headers={"Authorization": "Bearer invalid-token"},
        json={"query": "protein in cooked rice"},
    )

    assert response.status_code == 401


def test_rag_query_handles_empty_evidence(client, monkeypatch):
    authenticate()

    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/api/v1/rag/query",
        json={"query": "protein in unknown food"},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["retrieved_count"] == 0
    assert body["evidence"] == []
    assert body["citations"] == []
    assert body["verification"] is None
    assert "insufficient evidence" in body["answer"].lower()


def test_rag_query_reports_conflicting_claim(client, monkeypatch):
    authenticate()

    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        lambda *args, **kwargs: sample_evidence(),
    )

    response = client.post(
        "/api/v1/rag/query",
        json={
            "query": "protein in cooked rice",
            "claim": {
                "food_id": 10,
                "nutrient_key": "protein",
                "amount": 15,
                "unit": "g",
                "basis_g": 100,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["verification"]["status"] == "conflicting"


def test_rag_query_reports_incomparable_claim(client, monkeypatch):
    authenticate()

    evidence = sample_evidence()
    evidence[0]["provenance"]["basis_g"] = 200
    evidence[0]["provenance_records"] = [
        evidence[0]["provenance"]
    ]

    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        lambda *args, **kwargs: evidence,
    )

    response = client.post(
        "/api/v1/rag/query",
        json={
            "query": "protein in cooked rice",
            "claim": {
                "food_id": 10,
                "nutrient_key": "protein",
                "amount": 2.5,
                "unit": "g",
                "basis_g": 100,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["verification"]["status"] == "incomparable"


def test_rag_query_includes_conflict_and_measurement_warnings(
    client, monkeypatch
):
    authenticate()

    evidence = sample_evidence()
    evidence[0]["source_conflicts"] = [
        {"source": "secondary", "reason": "Different value"}
    ]
    evidence[0]["incomparable_measurements"] = [
        {"reason": "Different measurement basis"}
    ]

    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        lambda *args, **kwargs: evidence,
    )

    response = client.post(
        "/api/v1/rag/query",
        json={"query": "protein in cooked rice"},
    )

    assert response.status_code == 200
    answer = response.json()["answer"].lower()

    assert "source conflict" in answer
    assert "could not be made" in answer



def test_rag_query_does_not_support_claim_without_source_attribution(
    client, monkeypatch
):
    authenticate()

    evidence = sample_evidence()
    evidence[0]["provenance"].pop("source")
    evidence[0]["provenance_records"] = [
        evidence[0]["provenance"]
    ]

    monkeypatch.setattr(
        rag_routes,
        "retrieve_hybrid_evidence",
        lambda *args, **kwargs: evidence,
    )

    response = client.post(
        "/api/v1/rag/query",
        json={
            "query": "protein in cooked rice",
            "claim": {
                "food_id": 10,
                "nutrient_key": "protein",
                "amount": 2.5,
                "unit": "g",
                "basis_g": 100,
            },
        },
    )

    assert response.status_code == 200

    verification = response.json()["verification"]

    assert verification["status"] == "incomparable"
    assert verification["supporting_evidence"] == []
    assert len(verification["incomparable_evidence"]) == 1
    assert verification["incomparable_evidence"][0]["source"] is None
