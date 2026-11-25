from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func
from app.database.database import Base


class ResponseAction(Base):
    """Durable lifecycle for one account-specific incident response."""
    __tablename__ = "response_actions"
    __table_args__ = (
        UniqueConstraint("action_id", name="uq_response_actions_action_id"),
        UniqueConstraint("incident_id", name="uq_response_actions_incident_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    action_id = Column(String(36), nullable=False)
    incident_id = Column(String(20), nullable=False)
    user_id = Column(Integer, nullable=False)
    action = Column(String(64), nullable=False, default="revoke_user_sessions")
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    previous_token_version = Column(Integer, nullable=True)
    new_token_version = Column(Integer, nullable=True)
    last_error = Column(String(300), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())