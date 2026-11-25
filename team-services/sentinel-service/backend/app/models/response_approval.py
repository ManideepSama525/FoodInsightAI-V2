from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from app.database.database import Base


class ResponseApproval(Base):
    """Durable analyst approval linked to one policy evaluation and action."""

    __tablename__ = "response_approvals"

    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            name="uq_response_approvals_evaluation_id",
        ),
        UniqueConstraint(
            "action_id",
            name="uq_response_approvals_action_id",
        ),
        UniqueConstraint(
            "incident_id",
            name="uq_response_approvals_incident_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    evaluation_id = Column(String(36), nullable=False, index=True)
    action_id = Column(String(36), nullable=False)
    incident_id = Column(String(20), nullable=False)
    user_id = Column(Integer, nullable=False)

    status = Column(String(24), nullable=False, default="APPROVED_PENDING")
    attempt_count = Column(Integer, nullable=False, default=0)

    approved_by = Column(String(128), nullable=False)
    approval_reason = Column(String(300), nullable=False)

    last_error = Column(String(300), nullable=True)

    approved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.current_timestamp(),
    )
