from pathlib import Path

path = Path("backend/tests/test_api_integration.py")
source = path.read_text(encoding="utf-8")

if "def test_regulatory_ingest_requires_authentication" in source:
    raise SystemExit("Regulatory API tests already exist; refusing duplicate insertion.")

imports = '''
from backend.app.core.config import get_settings
from backend.app.models.evidence_document import EvidenceDocument
from backend.app.services_auth import decode_access_token
'''

anchor = "from backend.app.models.food import Food, FoodNutrient\n"
if source.count(anchor) != 1:
    raise SystemExit("Could not safely locate test imports.")
source = source.replace(anchor, anchor + imports)

tests = '''

def regulatory_payload(source_id="test-fssai-notice-001"):
    return {
        "records": [{
            "source_id": source_id,
            "title": "Food safety regulatory test notice",
            "content": "This is a test regulatory notice for API integration testing.",
            "authority": "Food Safety Authority",
            "jurisdiction": "India",
            "source_url": "https://www.fssai.gov.in/test-notice",
            "document_type": "food_safety_notice",
            "document_status": "active",
            "published_at": "2026-01-01T00:00:00Z",
            "effective_at": "2026-01-02T00:00:00Z",
            "last_checked_at": "2026-11-01T00:00:00Z",
        }]
    }


def regulatory_user_id(headers):
    return decode_access_token(headers["Authorization"].split(" ", 1)[1])


def test_regulatory_ingest_requires_authentication():
    response = client.post(
        "/api/v1/regulatory/ingest",
        json=regulatory_payload(),
    )
    assert response.status_code == 401


def test_regulatory_search_requires_authentication():
    response = client.get(
        "/api/v1/regulatory/search",
        params={"q": "food safety"},
    )
    assert response.status_code == 401


def test_regulatory_ingest_denies_when_allowlist_empty(monkeypatch):
    headers = recipe_auth_headers("regulatory-empty-admin@example.test")
    monkeypatch.setattr(
        get_settings(),
        "regulatory_admin_user_ids",
        [],
    )

    response = client.post(
        "/api/v1/regulatory/ingest",
        headers=headers,
        json=regulatory_payload("test-empty-admin-denied"),
    )
    assert response.status_code == 403


def test_regulatory_ingest_denies_non_admin(monkeypatch):
    headers = recipe_auth_headers("regulatory-non-admin@example.test")
    monkeypatch.setattr(
        get_settings(),
        "regulatory_admin_user_ids",
        [99999999],
    )

    response = client.post(
        "/api/v1/regulatory/ingest",
        headers=headers,
        json=regulatory_payload("test-non-admin-denied"),
    )
    assert response.status_code == 403


def test_regulatory_admin_can_ingest_and_search(monkeypatch):
    headers = recipe_auth_headers("regulatory-admin@example.test")
    user_id = regulatory_user_id(headers)

    monkeypatch.setattr(
        get_settings(),
        "regulatory_admin_user_ids",
        [user_id],
    )

    source_id = "test-regulatory-admin-success"
    payload = regulatory_payload(source_id)

    created = client.post(
        "/api/v1/regulatory/ingest",
        headers=headers,
        json=payload,
    )
    assert created.status_code == 200, created.text
    assert created.json() == {"created": 1, "updated": 0, "unchanged": 0}

    with TestingSession() as db:
        document = db.query(EvidenceDocument).filter_by(
            source_type="regulatory",
            source_id=source_id,
        ).one()
        assert document.status == "pending"
        assert document.provenance["record_type"] == "regulatory_evidence"
        assert document.provenance["official_domain_validated"] is True
        document.status = "indexed"
        db.commit()

    searched = client.get(
        "/api/v1/regulatory/search",
        headers=headers,
        params={"q": "regulatory test notice"},
    )
    assert searched.status_code == 200, searched.text

    result = next(
        item for item in searched.json()["results"]
        if item["source_id"] == source_id
    )
    assert result["provenance"]["authority"] == "Food Safety Authority"
    assert result["provenance"]["source_url"] == "https://www.fssai.gov.in/test-notice"


def test_regulatory_search_excludes_pending_and_unverified(monkeypatch):
    headers = recipe_auth_headers("regulatory-search-filter@example.test")
    monkeypatch.setattr(
        get_settings(),
        "regulatory_admin_user_ids",
        [],
    )

    with TestingSession() as db:
        db.query(EvidenceDocument).filter(
            EvidenceDocument.source_type == "regulatory",
            EvidenceDocument.source_id.in_([
                "test-regulatory-pending",
                "test-regulatory-unverified",
            ]),
        ).delete(synchronize_session=False)

        db.add_all([
            EvidenceDocument(
                source_type="regulatory",
                source_id="test-regulatory-pending",
                title="Food safety pending test",
                content="Food safety pending regulatory evidence test.",
                provenance={
                    "record_type": "regulatory_evidence",
                    "official_domain_validated": True,
                },
                content_hash="a" * 64,
                status="pending",
            ),
            EvidenceDocument(
                source_type="regulatory",
                source_id="test-regulatory-unverified",
                title="Food safety unverified test",
                content="Food safety unverified regulatory evidence test.",
                provenance={
                    "record_type": "other",
                    "official_domain_validated": False,
                },
                content_hash="b" * 64,
                status="indexed",
            ),
        ])
        db.commit()

    response = client.get(
        "/api/v1/regulatory/search",
        headers=headers,
        params={"q": "food safety"},
    )
    assert response.status_code == 200, response.text
    returned_ids = {
        item["source_id"] for item in response.json()["results"]
    }
    assert "test-regulatory-pending" not in returned_ids
    assert "test-regulatory-unverified" not in returned_ids


def test_regulatory_duplicate_ingestion_is_idempotent(monkeypatch):
    headers = recipe_auth_headers("regulatory-idempotent@example.test")
    user_id = regulatory_user_id(headers)
    monkeypatch.setattr(
        get_settings(),
        "regulatory_admin_user_ids",
        [user_id],
    )

    payload = regulatory_payload("test-regulatory-idempotent")
    first = client.post(
        "/api/v1/regulatory/ingest",
        headers=headers,
        json=payload,
    )
    second = client.post(
        "/api/v1/regulatory/ingest",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["created"] == 1
    assert second.json()["unchanged"] == 1
'''

path.write_text(source + tests, encoding="utf-8")
print("Added 7 regulatory API security and integration tests.")
