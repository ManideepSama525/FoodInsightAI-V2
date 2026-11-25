from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base

class UserFoodProfile(Base):
    __tablename__ = "user_food_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    allergies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    intolerances: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    dietary_preferences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    goals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    disliked_foods: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cuisine_interests: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
