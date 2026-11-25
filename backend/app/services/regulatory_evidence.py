from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.evidence_document import EvidenceDocument
from backend.app.schemas.regulatory import RegulatoryEvidenceCreate


def _document_payload(
    record: RegulatoryEvidenceCreate,
) -> tuple[str, str, dict[str, Any]]:
    provenance = {
        "record_type": "regulatory_evidence",
        "authority": record.authority,
        "jurisdiction": record.jurisdiction,
        "source_url": record.source_url,
        "official_domain_validated": True,
        "document_type": record.document_type,
        "document_status": record.document_status,
        "published_at": record.published_at.isoformat(),
        "effective_at": (
            record.effective_at.isoformat()
            if record.effective_at else None
        ),
        "last_checked_at": record.last_checked_at.isoformat(),
    }

    content = "\n".join([
        f"Authority: {record.authority}",
        f"Jurisdiction: {record.jurisdiction}",
        f"Document type: {record.document_type}",
        f"Document status: {record.document_status}",
        f"Published: {record.published_at.isoformat()}",
        f"Effective: {record.effective_at.isoformat() if record.effective_at else 'Not specified'}",
        f"Official source: {record.source_url}",
        "",
        record.content,
    ])

    payload = json.dumps(
        {"title": record.title, "content": content, "provenance": provenance},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return content, content_hash, provenance


def ingest_regulatory_evidence(
    db: Session,
    records: list[RegulatoryEvidenceCreate],
) -> dict[str, int]:
    """Upsert curated regulatory records; caller owns the transaction."""
    counts = {"created": 0, "updated": 0, "unchanged": 0}

    seen_ids: set[str] = set()

    for record in records:
        if record.source_id in seen_ids:
            raise ValueError(
                f"Duplicate source_id in batch: {record.source_id}"
            )
        seen_ids.add(record.source_id)

        content, content_hash, provenance = _document_payload(record)

        existing = db.scalar(
            select(EvidenceDocument).where(
                EvidenceDocument.source_type == "regulatory",
                EvidenceDocument.source_id == record.source_id,
            )
        )

        if existing is None:
            db.add(EvidenceDocument(
                source_type="regulatory",
                source_id=record.source_id,
                title=record.title,
                content=content,
                provenance=provenance,
                content_hash=content_hash,
                status="pending",
            ))
            counts["created"] += 1
            continue

        if existing.content_hash == content_hash:
            counts["unchanged"] += 1
            continue

        existing.title = record.title
        existing.content = content
        existing.provenance = provenance
        existing.content_hash = content_hash
        existing.status = "pending"
        counts["updated"] += 1

    db.flush()
    return counts
