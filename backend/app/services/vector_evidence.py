from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.evidence_document import EvidenceDocument
from backend.app.services.embeddings import embedding_service
from backend.app.services.knowledge_graph import knowledge_graph
from backend.app.services.regulatory_assessment import is_current_regulatory_evidence


ALLOWED_SOURCE_TYPES = ("food", "nutrient", "shared_recipe", "regulatory")
VECTOR_INDEX_NAME = "evidence_embedding_idx"
NODE_CONSTRAINT_NAME = "evidence_source_key"


def _source_key(document: EvidenceDocument) -> str:
    return f"{document.source_type}:{document.source_id}"


def _eligible(document: EvidenceDocument) -> bool:
    if document.source_type not in ALLOWED_SOURCE_TYPES:
        return False
    if document.source_type == "shared_recipe":
        return document.provenance.get("owner_scope") == "shared"
    if document.source_type == "regulatory":
        provenance = document.provenance or {}
        required = (
            "authority",
            "jurisdiction",
            "source_url",
            "document_type",
            "document_status",
            "published_at",
            "last_checked_at",
        )
        return (
            provenance.get("record_type") == "regulatory_evidence"
            and provenance.get("official_domain_validated") is True
            and all(provenance.get(key) for key in required)
            and is_current_regulatory_evidence(provenance)
        )
    return True


def _eligible_regulatory_provenance(provenance: dict[str, Any]) -> bool:
    required = (
        "authority",
        "jurisdiction",
        "source_url",
        "document_type",
        "document_status",
        "published_at",
        "last_checked_at",
    )
    return (
        provenance.get("record_type") == "regulatory_evidence"
        and provenance.get("official_domain_validated") is True
        and all(provenance.get(key) for key in required)
        and is_current_regulatory_evidence(provenance)
    )


def ensure_vector_index() -> None:
    settings = get_settings()
    with knowledge_graph.driver.session(
        database=settings.neo4j_database
    ) as session:
        session.run(
            f"CREATE CONSTRAINT {NODE_CONSTRAINT_NAME} IF NOT EXISTS "
            "FOR (e:EvidenceDocument) REQUIRE e.source_key IS UNIQUE"
        ).consume()

        session.run(
            f"""
            CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
            FOR (e:EvidenceDocument) ON (e.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {settings.embedding_dimensions},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
        ).consume()

        session.run(
            "CALL db.awaitIndex($index_name, 300)",
            index_name=VECTOR_INDEX_NAME,
        ).consume()


def _existing_metadata(
    source_keys: list[str],
) -> dict[str, dict[str, Any]]:
    if not source_keys:
        return {}

    settings = get_settings()
    with knowledge_graph.driver.session(
        database=settings.neo4j_database
    ) as session:
        records = session.run(
            """
            UNWIND $keys AS source_key
            OPTIONAL MATCH (e:EvidenceDocument {source_key: source_key})
            RETURN source_key,
                   e.content_hash AS content_hash,
                   e.model_name AS model_name,
                   e.status AS status
            """,
            keys=source_keys,
        )
        return {
            record["source_key"]: {
                "content_hash": record["content_hash"],
                "model_name": record["model_name"],
                "status": record["status"],
            }
            for record in records
        }


def _write_vectors(rows: list[dict[str, Any]]) -> None:
    settings = get_settings()
    with knowledge_graph.driver.session(
        database=settings.neo4j_database
    ) as session:
        session.execute_write(
            lambda tx: tx.run(
                """
                UNWIND $rows AS row
                MERGE (e:EvidenceDocument {source_key: row.source_key})
                SET e.source_type = row.source_type,
                    e.source_id = row.source_id,
                    e.title = row.title,
                    e.content = row.content,
                    e.content_hash = row.content_hash,
                    e.model_name = row.model_name,
                    e.provenance_json = row.provenance_json,
                    e.embedding = row.embedding,
                    e.status = 'indexed'
                """,
                rows=rows,
            ).consume()
        )


def _mark_stale_documents(db: Session, batch_size: int) -> int:
    settings = get_settings()
    offset = 0
    processed = 0

    while True:
        documents = db.scalars(
            select(EvidenceDocument)
            .where(
                EvidenceDocument.status == "stale",
                EvidenceDocument.source_type.in_(ALLOWED_SOURCE_TYPES),
            )
            .order_by(EvidenceDocument.id.asc())
            .limit(batch_size)
            .offset(offset)
        ).all()

        if not documents:
            break

        eligible = [document for document in documents if _eligible(document)]
        keys = [_source_key(document) for document in eligible]

        if keys:
            with knowledge_graph.driver.session(
                database=settings.neo4j_database
            ) as session:
                session.execute_write(
                    lambda tx: tx.run(
                        """
                        UNWIND $keys AS source_key
                        MATCH (e:EvidenceDocument {source_key: source_key})
                        SET e.status = 'stale'
                        """,
                        keys=keys,
                    ).consume()
                )

        processed += len(documents)
        offset += len(documents)

    return processed


def index_evidence_documents(
    db: Session,
    batch_size: int | None = None,
    max_documents: int | None = None,
) -> dict[str, int]:
    """Incrementally index eligible SQL evidence into Neo4j."""
    settings = get_settings()
    size = settings.embedding_batch_size if batch_size is None else batch_size

    # Validate arguments before checking or contacting external services.
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 128:
        raise ValueError("batch_size must be an integer between 1 and 128")
    if max_documents is not None and (
        isinstance(max_documents, bool)
        or not isinstance(max_documents, int)
        or max_documents < 1
    ):
        raise ValueError("max_documents must be a positive integer or None")
    if not knowledge_graph.enabled:
        raise RuntimeError("Knowledge graph is disabled or not configured")

    ensure_vector_index()

    counts = {
        "examined": 0,
        "embedded": 0,
        "skipped_unchanged": 0,
        "stale_synced": 0,
    }

    offset = 0

    while True:
        if max_documents is not None:
            remaining = max_documents - counts["examined"]
            if remaining <= 0:
                break

        documents = db.scalars(
            select(EvidenceDocument)
            .where(
                EvidenceDocument.source_type.in_(ALLOWED_SOURCE_TYPES),
                EvidenceDocument.status != "stale",
            )
            .order_by(EvidenceDocument.id.asc())
            .limit(size)
            .offset(offset)
        ).all()

        if not documents:
            break

        eligible = [document for document in documents if _eligible(document)]
        if max_documents is not None:
            eligible = eligible[:remaining]
        counts["examined"] += len(eligible)

        keys = [_source_key(document) for document in eligible]
        existing = _existing_metadata(keys)

        to_embed = []

        for document in eligible:
            current = existing.get(_source_key(document), {})
            unchanged = (
                current.get("content_hash") == document.content_hash
                and current.get("model_name") == settings.embedding_model_name
                and current.get("status") == "indexed"
            )

            if unchanged:
                document.status = "indexed"
                counts["skipped_unchanged"] += 1
            else:
                to_embed.append(document)

        if to_embed:
            texts = [
                f"{document.title}\n{document.content}"
                for document in to_embed
            ]
            vectors = embedding_service.encode(texts, batch_size=size)

            if len(vectors) != len(to_embed):
                raise RuntimeError("Embedding count does not match document count")

            rows = []
            for document, vector in zip(to_embed, vectors, strict=True):
                if len(vector) != settings.embedding_dimensions:
                    raise RuntimeError("Unexpected embedding dimensions")

                rows.append({
                    "source_key": _source_key(document),
                    "source_type": document.source_type,
                    "source_id": document.source_id,
                    "title": document.title,
                    "content": document.content,
                    "content_hash": document.content_hash,
                    "model_name": settings.embedding_model_name,
                    "provenance_json": json.dumps(
                        document.provenance,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "embedding": vector,
                })

            # Neo4j write must succeed before SQL status is committed.
            _write_vectors(rows)

            for document in to_embed:
                document.status = "indexed"

            counts["embedded"] += len(to_embed)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        offset += len(documents)

        if max_documents is not None and counts["examined"] >= max_documents:
            break

    counts["stale_synced"] = _mark_stale_documents(db, size)
    return counts


def search_evidence(
    query: str,
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve semantically similar eligible evidence."""
    if not query or not query.strip():
        raise ValueError("Search query cannot be empty")
    if not 1 <= top_k <= 50:
        raise ValueError("top_k must be between 1 and 50")
    if not knowledge_graph.enabled:
        raise RuntimeError("Knowledge graph is disabled or not configured")

    settings = get_settings()
    vector = embedding_service.encode([query], query=True)[0]
    candidates = min(max(top_k * 8, 40), 200)

    with knowledge_graph.driver.session(
        database=settings.neo4j_database
    ) as session:
        records = session.run(
            """
            CALL db.index.vector.queryNodes(
                $index_name, $candidate_count, $embedding
            )
            YIELD node, score
            WHERE node.status = 'indexed'
              AND node.source_type IN $source_types
              AND (
                node.source_type <> 'shared_recipe'
                OR node.provenance_json CONTAINS '"owner_scope": "shared"'
                OR node.provenance_json CONTAINS '"owner_scope":"shared"'
              )
            RETURN node.source_type AS source_type,
                   node.source_id AS source_id,
                   node.title AS title,
                   node.content AS content,
                   node.provenance_json AS provenance_json,
                   node.content_hash AS content_hash,
                   score
            ORDER BY score DESC
            LIMIT $top_k
            """,
            index_name=VECTOR_INDEX_NAME,
            candidate_count=candidates,
            embedding=vector,
            source_types=list(ALLOWED_SOURCE_TYPES),
            top_k=candidates,
        )

        results = []
        for record in records:
            try:
                provenance = json.loads(record["provenance_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                continue

            if record["source_type"] == "shared_recipe":
                if provenance.get("owner_scope") != "shared":
                    continue

            if record["source_type"] == "regulatory":
                if not _eligible_regulatory_provenance(provenance):
                    continue

            result = {
                "source_type": record["source_type"],
                "source_id": record["source_id"],
                "title": record["title"],
                "content": record["content"],
                "provenance": provenance,
                "content_hash": record["content_hash"],
                "score": float(record["score"]),
            }
            if record["source_type"] == "regulatory":
                from backend.app.services.regulatory_assessment import assess_regulatory_evidence
                result["regulatory_assessment"] = assess_regulatory_evidence(provenance)
            results.append(result)

        return results[:top_k]
