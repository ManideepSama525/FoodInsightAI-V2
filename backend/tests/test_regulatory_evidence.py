from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.models.evidence_document import EvidenceDocument
from backend.app.schemas.regulatory import RegulatoryEvidenceCreate
from backend.app.services.regulatory_evidence import ingest_regulatory_evidence
from backend.app.services.regulatory_assessment import (
    assess_regulatory_evidence,
    is_current_regulatory_evidence,
)


NOW = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)


def record(**overrides):
    values = {
        "source_id": "FSSAI-NOTICE-001",
        "title": "Food safety guidance notice",
        "content": "Official guidance content with sufficient detail for indexing.",
        "authority": "Food Safety and Standards Authority of India",
        "jurisdiction": "India",
        "source_url": "https://www.fssai.gov.in/example-notice",
        "document_type": "guidance",
        "document_status": "active",
        "published_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
        "effective_at": None,
        "last_checked_at": NOW,
    }
    values.update(overrides)
    return RegulatoryEvidenceCreate(**values)


def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_rejects_non_https_and_unapproved_domains():
    with pytest.raises(ValueError, match="HTTPS"):
        record(source_url="http://www.fssai.gov.in/notice")

    with pytest.raises(ValueError, match="approved official"):
        record(source_url="https://example.com/fssai-notice")


def test_rejects_invalid_dates():
    with pytest.raises(ValueError, match="effective_at"):
        record(effective_at=datetime(2026, 10, 1, tzinfo=timezone.utc))


def test_ingests_regulatory_evidence_as_pending():
    engine, db = make_session()
    try:
        result = ingest_regulatory_evidence(db, [record()])
        db.commit()

        document = db.scalar(
            select(EvidenceDocument).where(
                EvidenceDocument.source_type == "regulatory"
            )
        )

        assert result == {"created": 1, "updated": 0, "unchanged": 0}
        assert document.status == "pending"
        assert document.provenance["authority"].startswith("Food Safety")
        assert document.provenance["jurisdiction"] == "India"
        assert document.provenance["official_domain_validated"] is True
        assert document.provenance["document_type"] == "guidance"
        assert "Official source:" in document.content
    finally:
        db.close()
        engine.dispose()


def test_ingestion_is_idempotent():
    engine, db = make_session()
    try:
        first = ingest_regulatory_evidence(db, [record()])
        db.commit()
        second = ingest_regulatory_evidence(db, [record()])
        db.commit()

        assert first["created"] == 1
        assert second["unchanged"] == 1

        documents = db.scalars(
            select(EvidenceDocument).where(
                EvidenceDocument.source_type == "regulatory"
            )
        ).all()
        assert len(documents) == 1
    finally:
        db.close()
        engine.dispose()


def test_changed_record_is_updated_and_reindexed():
    engine, db = make_session()
    try:
        ingest_regulatory_evidence(db, [record()])
        db.commit()

        document = db.scalar(
            select(EvidenceDocument).where(
                EvidenceDocument.source_type == "regulatory"
            )
        )
        document.status = "indexed"
        db.commit()

        result = ingest_regulatory_evidence(
            db,
            [record(document_status="amended")],
        )
        db.commit()

        assert result["updated"] == 1
        assert document.status == "pending"
        assert document.provenance["document_status"] == "amended"
    finally:
        db.close()
        engine.dispose()


def test_duplicate_source_id_in_same_batch_is_rejected():
    engine, db = make_session()
    try:
        with pytest.raises(ValueError, match="Duplicate source_id"):
            ingest_regulatory_evidence(db, [record(), record()])
    finally:
        db.close()
        engine.dispose()


def test_active_regulatory_evidence_within_freshness_window_is_eligible():
    provenance = {
        "record_type": "regulatory_evidence",
        "official_domain_validated": True,
        "document_status": "active",
        "last_checked_at": NOW.isoformat(),
    }

    assert is_current_regulatory_evidence(provenance)

    assessment = assess_regulatory_evidence(
        provenance,
        now=NOW,
    )

    assert assessment["assessment_status"] == "current_check"
    assert assessment["eligible_for_current_retrieval"] is True


def test_stale_active_regulatory_evidence_is_excluded():
    provenance = {
        "record_type": "regulatory_evidence",
        "official_domain_validated": True,
        "document_status": "active",
        "last_checked_at": "2026-01-01T00:00:00+00:00",
    }

    assessment = assess_regulatory_evidence(
        provenance,
        now=NOW,
    )

    assert assessment["revalidation_due"] is True
    assert assessment["eligible_for_current_retrieval"] is False
    assert assessment["assessment_status"] == "revalidation_due"
    assert not is_current_regulatory_evidence(provenance)


@pytest.mark.parametrize(
    "checked_at",
    [None, "invalid-date"],
)
def test_missing_or_malformed_check_date_is_excluded(checked_at):
    provenance = {
        "record_type": "regulatory_evidence",
        "official_domain_validated": True,
        "document_status": "active",
        "last_checked_at": checked_at,
    }

    assessment = assess_regulatory_evidence(
        provenance,
        now=NOW,
    )

    assert assessment["revalidation_due"] is True
    assert assessment["eligible_for_current_retrieval"] is False
    assert not is_current_regulatory_evidence(provenance)


def test_non_active_regulatory_evidence_is_excluded():
    provenance = {
        "record_type": "regulatory_evidence",
        "official_domain_validated": True,
        "document_status": "withdrawn",
        "last_checked_at": NOW.isoformat(),
    }

    assert not is_current_regulatory_evidence(provenance)
