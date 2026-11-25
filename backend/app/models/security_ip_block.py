"""Auditable, temporary source-IP containment records."""
from datetime import datetime

from sqlalchemy import (
    DateTime, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class SecurityIPBlock(Base):
    __tablename__ = "security_ip_blocks"
    __table_args__ = (
        UniqueConstraint(
            "action_id",
            name="uq_security_ip_blocks_action_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True,
    )
    action_id: Mapped[str] = mapped_column(
        String(36), nullable=False,
    )
    incident_id: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
    )
    source_ip: Mapped[str] = mapped_column(
        String(45), nullable=False, index=True,
    )
    reason: Mapped[str] = mapped_column(
        String(500), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False,
    )
    performed_by: Mapped[str] = mapped_column(
        String(64), nullable=False,
    )
    result: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
