from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.food import Food

def search_local_foods(db: Session, query: str, limit: int = 20) -> list[Food]:
    cleaned = " ".join(query.casefold().split())
    if not cleaned:
        return list_foods(db, limit)
    safe_limit = max(1, min(limit, 50))
    statement = (
        select(Food).options(selectinload(Food.nutrients))
        .where(or_(Food.normalized_name.contains(cleaned), Food.name.ilike(f"%{cleaned}%")))
        .order_by(Food.name.asc()).limit(safe_limit)
    )
    return list(db.scalars(statement).unique().all())

def list_foods(db: Session, limit: int = 20) -> list[Food]:
    safe_limit = max(1, min(limit, 50))
    statement = select(Food).options(selectinload(Food.nutrients)).order_by(Food.id.desc()).limit(safe_limit)
    return list(db.scalars(statement).unique().all())

def get_food_by_source_id(db: Session, source: str, external_id: str) -> Food | None:
    statement = select(Food).options(selectinload(Food.nutrients)).where(
        Food.source == source, Food.external_id == external_id
    )
    return db.scalars(statement).first()

def save_food(db: Session, food: Food) -> Food:
    existing = get_food_by_source_id(db, food.source, food.external_id) if food.external_id else None
    if existing:
        existing.name = food.name
        existing.normalized_name = food.normalized_name
        existing.category = food.category
        existing.source_url = food.source_url
        existing.description = food.description
        existing.nutrients.clear()
        existing.nutrients.extend(food.nutrients)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    db.add(food)
    db.commit()
    db.refresh(food)
    return food
