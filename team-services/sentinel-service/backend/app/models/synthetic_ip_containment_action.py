"""Separate durable audit for synthetic IP containment actions."""
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Integer, String,
    UniqueConstraint, func,
)
from app.database.database import Base


class SyntheticIPContainmentAction(Base):
    __tablename__ = "synthetic_ip_containment_actions"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_synthetic_ip_action_id"),
        UniqueConstraint("incident_id", name="uq_synthetic_ip_incident_id"),
    )

    id = Column(Integer, primary_key=True)
    action_id = Column(String(36), nullable=False)
    incident_id = Column(String(20), nullable=False)
    source_ip = Column(String(45), nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    confirmed_expires_at = Column(DateTime, nullable=True)
    last_error = Column(String(300), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
