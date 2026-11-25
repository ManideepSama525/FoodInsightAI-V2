from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.database.database import Base


class ResponsePolicyDecision(Base):
    """Immutable-history record for an analyst-authorized policy evaluation."""

    __tablename__ = "response_policy_decisions"

    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            name="uq_response_policy_evaluation_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    evaluation_id = Column(String(36), nullable=False)
    incident_id = Column(String(20), nullable=False, index=True)

    policy_version = Column(String(20), nullable=False)
    decision = Column(String(48), nullable=False)
    recommended_action = Column(String(64), nullable=False)

    severity = Column(String(20), nullable=True)
    confidence_score = Column(Float, nullable=False, default=0.0)

    evidence_count = Column(Integer, nullable=False, default=0)
    evidence_verified = Column(Boolean, nullable=False, default=False)

    requires_approval = Column(Boolean, nullable=False, default=False)
    automation_authorized = Column(Boolean, nullable=False, default=False)
    execution_mode = Column(String(20), nullable=False, default="DRY_RUN")

    trigger_event_id = Column(String(64), nullable=True)
    reason = Column(Text, nullable=False)

    actor = Column(String(64), nullable=False, default="authorized_request")

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
