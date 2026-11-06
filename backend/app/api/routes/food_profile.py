from datetime import timezone
from typing import Annotated
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.models.food import Food
from backend.app.models.recipe import Recipe
from backend.app.models.user import User
from backend.app.models.user_food_profile import UserFoodProfile
from backend.app.services.food_safety import assess_ingredients as _assess, _profile_read
from backend.app.services.recommendations import recommend_foods
from backend.app.schemas.food_profile import (
    FoodProfileRead, FoodProfileUpdate, FoodSafetyMatch,
    FoodSafetyRead, FoodSafetyRequest,
)

router = APIRouter(prefix="/food-profile", tags=["personalized food safety"])

@router.get("", response_model=FoodProfileRead)
def get_food_profile(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FoodProfileRead:
    profile = db.scalar(select(UserFoodProfile).where(UserFoodProfile.user_id == user.id))
    return _profile_read(profile)


@router.put("", response_model=FoodProfileRead)
def update_food_profile(
    payload: FoodProfileUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FoodProfileRead:
    profile = db.scalar(select(UserFoodProfile).where(UserFoodProfile.user_id == user.id))
    if profile is None:
        profile = UserFoodProfile(user_id=user.id)
        db.add(profile)

    profile.allergies = [item.model_dump() for item in payload.allergies]
    profile.intolerances = [item.model_dump() for item in payload.intolerances]
    profile.dietary_preferences = payload.dietary_preferences
    profile.goals = payload.goals
    profile.disliked_foods = payload.disliked_foods
    profile.cuisine_interests = payload.cuisine_interests
    db.commit()
    db.refresh(profile)
    return _profile_read(profile)




@router.get("/recommendations")
def food_recommendations(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 10,
) -> dict:
    if limit < 1 or limit > 30:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 30.")

    profile = db.scalar(
        select(UserFoodProfile).where(UserFoodProfile.user_id == user.id)
    )
    foods = db.scalars(
        select(Food).options(
            selectinload(Food.nutrients)
        ).order_by(Food.name.asc()).limit(1000)
    ).unique().all()

    return recommend_foods(foods, profile, limit)
@router.post("/assess", response_model=FoodSafetyRead)
def assess_ingredients(
    payload: FoodSafetyRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FoodSafetyRead:
    profile = db.scalar(select(UserFoodProfile).where(UserFoodProfile.user_id == user.id))
    return _assess([item.model_dump() for item in payload.ingredients], profile)


@router.get("/recipes/{recipe_id}/assess", response_model=FoodSafetyRead)
def assess_recipe(
    recipe_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FoodSafetyRead:
    recipe = db.scalar(
        select(Recipe).where(
            Recipe.id == recipe_id,
            (Recipe.user_id == user.id) | (Recipe.user_id.is_(None)),
        )
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    ingredients = [{"name": item.ingredient_name, "confidence": 1.0} for item in recipe.ingredients]
    if not ingredients:
        raise HTTPException(status_code=422, detail="This recipe has no ingredient records.")

    profile = db.scalar(select(UserFoodProfile).where(UserFoodProfile.user_id == user.id))
    return _assess(ingredients, profile)
