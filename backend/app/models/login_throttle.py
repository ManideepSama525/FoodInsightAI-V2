from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class LoginThrottleState(Base):
    __tablename__ = "login_throttle_states"

    account_hash: Mapped[str] = mapped_column(
        String(64), primary_key=True
    )

    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )

    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )
