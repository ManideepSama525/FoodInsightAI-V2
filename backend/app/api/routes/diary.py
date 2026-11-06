from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.models.diary import DiaryEntry
from backend.app.models.food import Food
from backend.app.models.user import User
from backend.app.schemas.diary import DiaryEntryCreate, DiaryEntryRead

router = APIRouter(prefix="/diary", tags=["food diary"])


def _serialize(entry: DiaryEntry, food_name: str) -> DiaryEntryRead:
    return DiaryEntryRead(
        id=entry.id,
        food_id=entry.food_id,
        food_name=food_name,
        quantity_g=entry.quantity_g,
        meal_type=entry.meal_type,
        consumed_at=entry.consumed_at,
        notes=entry.notes,
    )


@router.post("", response_model=DiaryEntryRead, status_code=status.HTTP_201_CREATED)
def create_diary_entry(
    payload: DiaryEntryCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DiaryEntryRead:
    food = db.get(Food, payload.food_id)
    if food is None:
        raise HTTPException(status_code=404, detail="Food record not found.")

    entry = DiaryEntry(
        user_id=user.id,
        food_id=food.id,
        quantity_g=payload.quantity_g,
        meal_type=payload.meal_type,
        consumed_at=payload.consumed_at or datetime.now(timezone.utc),
        notes=payload.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _serialize(entry, food.name)


@router.get("", response_model=list[DiaryEntryRead])
def list_diary_entries(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DiaryEntryRead]:
    rows = db.execute(
        select(DiaryEntry, Food.name)
        .join(Food, Food.id == DiaryEntry.food_id)
        .where(DiaryEntry.user_id == user.id)
        .order_by(DiaryEntry.consumed_at.desc(), DiaryEntry.id.desc())
        .limit(limit)
    ).all()
    return [_serialize(entry, food_name) for entry, food_name in rows]


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diary_entry(
    entry_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    entry = db.scalar(
        select(DiaryEntry).where(
            DiaryEntry.id == entry_id,
            DiaryEntry.user_id == user.id,
        )
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Diary entry not found.")
    db.delete(entry)
    db.commit()