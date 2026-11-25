"""Synthetic-account-only Sentinel detection response audit (no IP blocking)."""
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class SentinelLoginHold(Base):
    __tablename__ = "sentinel_synthetic_login_holds"

    account_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    incident_id: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
