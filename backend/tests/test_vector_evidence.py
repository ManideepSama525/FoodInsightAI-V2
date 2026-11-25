import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.services import vector_evidence as vector


class FakeScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


def make_document(
    source_type="food",
    source_id="101",
    status="pending",
    provenance=None,
):
    return SimpleNamespace(
        id=1,
        source_type=source_type,
        source_id=source_id,
        title="Apple",
        content="Food: Apple",
        content_hash="hash-apple",
        status=status,
        provenance=provenance or {"record_type": "food_catalog"},
    )


def configure_index_mocks(monkeypatch, documents, metadata=None):
    settings = SimpleNamespace(
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimensions=384,
        embedding_batch_size=32,
        neo4j_database="neo4j",
    )
    monkeypatch.setattr(vector, "get_settings", lambda: settings)
    monkeypatch.setattr(vector, "ensure_vector_index", lambda: None)
    monkeypatch.setattr(
        vector,
        "knowledge_graph",
        SimpleNamespace(enabled=True),
    )

    results = [FakeScalarResult(documents), FakeScalarResult([]), FakeScalarResult([])]
    db = MagicMock()
    db.scalars.side_effect = results

    monkeypatch.setattr(
        vector,
        "_existing_metadata",
        lambda keys: metadata or {},
    )

    return db


def test_source_key_and_private_recipe_exclusion():
    public_recipe = make_document(
        source_type="shared_recipe",
        source_id="12",
        provenance={"owner_scope": "shared"},
    )
    private_recipe = make_document(
        source_type="shared_recipe",
        source_id="13",
        provenance={"owner_scope": "private"},
    )

    assert vector._source_key(public_recipe) == "shared_recipe:12"
    assert vector._eligible(public_recipe)
    assert not vector._eligible(private_recipe)


def test_index_embeds_pending_document_and_commits_after_write(monkeypatch):
    document = make_document()
    db = configure_index_mocks(monkeypatch, [document])

    encoded = []
    written = []

    monkeypatch.setattr(
        vector.embedding_service,
        "encode",
        lambda texts, **kwargs: (
            encoded.extend(texts) or [[0.01] * 384 for _ in texts]
        ),
    )
    monkeypatch.setattr(
        vector,
        "_write_vectors",
        lambda rows: written.extend(rows),
    )

    result = vector.index_evidence_documents(db, batch_size=8)

    assert result["examined"] == 1
    assert result["embedded"] == 1
    assert result["skipped_unchanged"] == 0
    assert document.status == "indexed"
    assert len(encoded) == 1
    assert len(written) == 1
    assert written[0]["source_key"] == "food:101"
    assert len(written[0]["embedding"]) == 384
    assert json.loads(written[0]["provenance_json"])["record_type"] == "food_catalog"
    db.commit.assert_called_once()


def test_index_skips_unchanged_document(monkeypatch):
    document = make_document(status="pending")
    metadata = {
        "food:101": {
            "content_hash": "hash-apple",
            "model_name": "BAAI/bge-small-en-v1.5",
            "status": "indexed",
        }
    }
    db = configure_index_mocks(monkeypatch, [document], metadata)

    monkeypatch.setattr(
        vector.embedding_service,
        "encode",
        lambda *args, **kwargs: pytest.fail("Unchanged document was re-embedded"),
    )
    monkeypatch.setattr(
        vector,
        "_write_vectors",
        lambda rows: pytest.fail("Unchanged vector was rewritten"),
    )

    result = vector.index_evidence_documents(db)

    assert result["skipped_unchanged"] == 1
    assert result["embedded"] == 0
    assert document.status == "indexed"
    db.commit.assert_called_once()


def test_index_excludes_private_recipe(monkeypatch):
    private_recipe = make_document(
        source_type="shared_recipe",
        source_id="99",
        provenance={"owner_scope": "private"},
    )
    db = configure_index_mocks(monkeypatch, [private_recipe])

    monkeypatch.setattr(
        vector.embedding_service,
        "encode",
        lambda *args, **kwargs: pytest.fail("Private recipe was embedded"),
    )
    monkeypatch.setattr(
        vector,
        "_write_vectors",
        lambda rows: pytest.fail("Private recipe was written to Neo4j"),
    )

    result = vector.index_evidence_documents(db)

    assert result["examined"] == 0
    assert result["embedded"] == 0
    assert private_recipe.status == "pending"


def test_index_rejects_invalid_batch_size():
    db = MagicMock()
    with pytest.raises(ValueError, match="batch_size"):
        vector.index_evidence_documents(db, batch_size=0)


def test_search_rejects_empty_query_and_invalid_limit():
    with pytest.raises(ValueError, match="empty"):
        vector.search_evidence(" ")

    with pytest.raises(ValueError, match="top_k"):
        vector.search_evidence("apple", top_k=0)


def test_search_returns_only_shared_recipe_provenance(monkeypatch):
    safe_record = {
        "source_type": "shared_recipe",
        "source_id": "12",
        "title": "Apple salad",
        "content": "Apple and vegetables",
        "provenance_json": json.dumps({"owner_scope": "shared"}),
        "content_hash": "hash-safe",
        "score": 0.91,
    }
    private_record = {
        "source_type": "shared_recipe",
        "source_id": "13",
        "title": "Private recipe",
        "content": "Private content",
        "provenance_json": json.dumps({"owner_scope": "private"}),
        "content_hash": "hash-private",
        "score": 0.99,
    }
    food_record = {
        "source_type": "food",
        "source_id": "101",
        "title": "Apple",
        "content": "Food: Apple",
        "provenance_json": json.dumps({"record_type": "food_catalog"}),
        "content_hash": "hash-food",
        "score": 0.88,
    }

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def run(self, query, **kwargs):
            assert "node.status = 'indexed'" in query
            assert "node.source_type IN $source_types" in query
            return [safe_record, private_record, food_record]

    class FakeDriver:
        def session(self, **kwargs):
            return FakeSession()

    monkeypatch.setattr(
        vector,
        "get_settings",
        lambda: SimpleNamespace(neo4j_database="neo4j"),
    )
    monkeypatch.setattr(
        vector,
        "knowledge_graph",
        SimpleNamespace(enabled=True, driver=FakeDriver()),
    )
    monkeypatch.setattr(
        vector.embedding_service,
        "encode",
        lambda texts, **kwargs: [[0.01] * 384],
    )

    results = vector.search_evidence("apple nutrition", top_k=5)

    assert len(results) == 2
    assert results[0]["source_id"] == "12"
    assert results[0]["provenance"]["owner_scope"] == "shared"
    assert results[1]["source_type"] == "food"
    assert all(item["source_id"] != "13" for item in results)

def test_index_respects_max_documents_limit(monkeypatch):
    documents = [
        make_document(source_id=str(index))
        for index in range(1, 9)
    ]
    db = MagicMock()
    db.scalars.side_effect = [
        FakeScalarResult(documents[:4]),
        FakeScalarResult(documents[4:]),
    ]

    settings = SimpleNamespace(
        embedding_model_name="BAAI/bge-small-en-v1.5",
        embedding_dimensions=384,
        embedding_batch_size=32,
        neo4j_database="neo4j",
    )
    monkeypatch.setattr(vector, "get_settings", lambda: settings)
    monkeypatch.setattr(vector, "ensure_vector_index", lambda: None)
    monkeypatch.setattr(
        vector, "knowledge_graph", SimpleNamespace(enabled=True)
    )
    monkeypatch.setattr(vector, "_existing_metadata", lambda keys: {})
    monkeypatch.setattr(vector, "_mark_stale_documents", lambda db, size: 0)

    encoded = []
    written = []

    monkeypatch.setattr(
        vector.embedding_service,
        "encode",
        lambda texts, **kwargs: (
            encoded.extend(texts) or [[0.01] * 384 for _ in texts]
        ),
    )
    monkeypatch.setattr(
        vector,
        "_write_vectors",
        lambda rows: written.extend(rows),
    )

    result = vector.index_evidence_documents(
        db,
        batch_size=4,
        max_documents=5,
    )

    assert result["examined"] == 5
    assert result["embedded"] == 5
    assert len(encoded) == 5
    assert len(written) == 5
    assert all(document.status == "indexed" for document in documents[:5])
    assert all(document.status == "pending" for document in documents[5:])
    assert db.commit.call_count == 2


@pytest.mark.parametrize("invalid_limit", [0, -1, True, 1.5, "5"])
def test_index_rejects_invalid_max_documents(invalid_limit):
    db = MagicMock()

    with pytest.raises(ValueError, match="max_documents"):
        vector.index_evidence_documents(
            db,
            max_documents=invalid_limit,
        )

    db.scalars.assert_not_called()


def test_regulatory_document_is_eligible_only_with_validated_provenance():
    valid = make_document(
        source_type="regulatory",
        source_id="NOTICE-1",
        provenance={
            "record_type": "regulatory_evidence",
            "official_domain_validated": True,
            "authority": "FSSAI",
            "jurisdiction": "India",
            "source_url": "https://www.fssai.gov.in/notice",
            "document_type": "guidance",
            "document_status": "active",
            "published_at": "2026-11-01T00:00:00+00:00",
            "last_checked_at": "2026-11-13T00:00:00+00:00",
        },
    )
    invalid = make_document(
        source_type="regulatory",
        source_id="NOTICE-2",
        provenance={"record_type": "regulatory_evidence"},
    )

    assert vector._eligible(valid)
    assert not vector._eligible(invalid)


def test_index_excludes_unverified_regulatory_document(monkeypatch):
    document = make_document(
        source_type="regulatory",
        source_id="NOTICE-3",
        provenance={
            "record_type": "regulatory_evidence",
            "official_domain_validated": False,
        },
    )
    db = configure_index_mocks(monkeypatch, [document])

    monkeypatch.setattr(
        vector.embedding_service,
        "encode",
        lambda *args, **kwargs: pytest.fail("Unverified evidence was embedded"),
    )
    monkeypatch.setattr(
        vector,
        "_write_vectors",
        lambda rows: pytest.fail("Unverified evidence was indexed"),
    )

    result = vector.index_evidence_documents(db)

    assert result["examined"] == 0
    assert result["embedded"] == 0
    assert document.status == "pending"
