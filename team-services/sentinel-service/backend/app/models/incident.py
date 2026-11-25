from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Boolean

from app.database.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    # ------------------------------------------------
    # Primary Keys
    # ------------------------------------------------

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    incident_id = Column(
        String(20),
        unique=True,
        nullable=False,
    )

    # ------------------------------------------------
    # Incident Information
    # ------------------------------------------------

    attack_type = Column(
        String(100),
        nullable=False,
    )

    severity = Column(
        String(20),
        nullable=False,
    )

    source_ip = Column(
        String(50),
        nullable=False,
    )

    target = Column(
        String(255),
        nullable=False,
    )

    description = Column(
        String,
        nullable=False,
    )

    # ------------------------------------------------
    # AI Analysis
    # ------------------------------------------------

    ai_explanation = Column(
        String,
        nullable=False,
    )

    confidence = Column(
        Float,
        nullable=False,
    )

    ai_prediction = Column(
        String(100),
        nullable=True,
    )

    ai_confidence = Column(
        Float,
        nullable=True,
    )

    ai_model = Column(
        String(100),
        nullable=True,
    )

    # ------------------------------------------------
    # AI Threat Risk Score
    # ------------------------------------------------

    threat_score = Column(
        Float,
        nullable=True,
        default=0,
    )

    # ------------------------------------------------
    # Alert Acknowledgement
    # ------------------------------------------------

    acknowledged = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    # ------------------------------------------------
    # Response
    # ------------------------------------------------

    response_action = Column(
        String,
        nullable=False,
    )

    status = Column(
        String(20),
        default="Active",
    )

    # ------------------------------------------------
    # Account-specific response attribution (nullable for legacy incidents)
    # ------------------------------------------------

    target_user_id = Column(String(64), nullable=True, index=True)
    target_account_hash = Column(String(64), nullable=True, index=True)
    trigger_event_id = Column(String(64), nullable=True, index=True)

    # ------------------------------------------------
    # Timestamp
    # ------------------------------------------------

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )