from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.base import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        Index("ix_foods_name", "name"),
        Index("ix_foods_source_external_id", "source", "external_id"),
        UniqueConstraint("source", "external_id", name="uq_food_source_external_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    nutrients: Mapped[list["FoodNutrient"]] = relationship(back_populates="food", cascade="all, delete-orphan")

class FoodNutrient(Base):
    __tablename__ = "food_nutrients"
    __table_args__ = (UniqueConstraint("food_id", "nutrient_key", name="uq_food_nutrient_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"), index=True)
    nutrient_key: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 5), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    basis_g: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("100"))
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_nutrient_id: Mapped[str | None] = mapped_column(String(100))
    food: Mapped[Food] = relationship(back_populates="nutrients")
