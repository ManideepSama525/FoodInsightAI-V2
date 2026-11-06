from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from backend.app.db.session import get_db
from backend.app.integrations.usda.client import USDAClient, USDAClientError
from backend.app.integrations.usda.mapper import map_usda_food, map_usda_search_result
from backend.app.models.food import Food
from backend.app.schemas.nutrition import FoodRead, FoodSearchResponse
from backend.app.services.nutrition.calculator import calculate_food_nutrition
from backend.app.services.nutrition.catalog import get_food_by_source_id, save_food, search_local_foods

router = APIRouter(prefix="/nutrition", tags=["nutrition"])

@router.get("/foods", response_model=list[FoodRead])
def search_local_catalog(
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[Food]:
    return search_local_foods(db, q or "", limit)

@router.get("/foods/usda/search", response_model=FoodSearchResponse)
async def search_usda_catalog(
    q: str = Query(min_length=1, max_length=120),
    page_size: int = Query(default=10, ge=1, le=50),
    page_number: int = Query(default=1, ge=1),
) -> dict:
    try:
        payload = await USDAClient().search_foods(q, page_size, page_number)
    except (USDAClientError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="USDA FoodData Central search is unavailable.") from exc
    results = [map_usda_search_result(item) for item in payload.get("foods", [])]
    return {"query": q, "count": len(results), "results": results}

@router.post("/foods/usda/{fdc_id}/import", response_model=FoodRead)
async def import_usda_food(fdc_id: int, db: Session = Depends(get_db)) -> Food:
    existing = get_food_by_source_id(db, "usda_fdc", str(fdc_id))
    if existing:
        return existing
    try:
        payload = await USDAClient().get_food(fdc_id)
        food = map_usda_food(payload)
    except (USDAClientError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Unable to retrieve this USDA food record.") from exc
    return save_food(db, food)

@router.get("/foods/{food_id}/calculate")
def calculate_food(
    food_id: int,
    quantity_g: Decimal = Query(gt=0, le=100000),
    quantity_source: str = Query(default="user_entered", pattern="^(user_entered|estimated)$"),
    db: Session = Depends(get_db),
) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    food = db.scalars(
        select(Food)
        .options(selectinload(Food.nutrients))
        .where(Food.id == food_id)
    ).unique().first()

    if food is None:
        raise HTTPException(status_code=404, detail="Food not found.")

    return calculate_food_nutrition(food, quantity_g, quantity_source)
