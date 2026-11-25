from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceDocument(Base):
    """Persistent, source-attributed evidence used by hybrid retrieval."""

    __tablename__ = "evidence_documents"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_evidence_source",
        ),
        Index("ix_evidence_documents_source_type", "source_type"),
        Index("ix_evidence_documents_content_hash", "content_hash"),
        Index("ix_evidence_documents_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )