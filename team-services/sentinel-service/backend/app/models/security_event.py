from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from app.database.database import Base


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(Integer, primary_key=True, index=True)

    event_id = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    source = Column(String(64), nullable=False)
    event_type = Column(String(64), nullable=False)

    category = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=True)
    risk_score = Column(Float, nullable=True)

    client_id = Column(String(128), nullable=True, index=True)
    source_ip = Column(String(45), nullable=True, index=True)
    user_id = Column(String(64), nullable=True)
    account_id_hash = Column(String(64), nullable=True, index=True)

    method = Column(String(12), nullable=True)
    path = Column(String(512), nullable=True)
    status_code = Column(Integer, nullable=True)

    detection_rule_id = Column(String(120), nullable=True)
    description = Column(Text, nullable=True)
    action_taken = Column(String(80), nullable=True)

    occurred_at = Column(DateTime, nullable=False)
    received_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    __table_args__ = (
        Index(
            "ix_security_events_client_occurred",
            "client_id",
            "occurred_at",
        ),
        Index(
            "ix_security_events_category_occurred",
            "category",
            "occurred_at",
        ),
    )