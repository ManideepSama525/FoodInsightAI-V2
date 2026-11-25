from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.models.recipe import Recipe
from backend.app.models.user import User
from backend.app.schemas.food_authenticity import (
    RecipeConsistencyRequest,
    RecipeConsistencyResponse,
)
from backend.app.services.recipe_consistency import analyze_recipe_consistency


router = APIRouter(
    prefix="/food-authenticity",
    tags=["food-authenticity"],
)


@router.post(
    "/recipe-consistency",
    response_model=RecipeConsistencyResponse,
    summary="Compare supplied ingredients with a stored recipe",
    description=(
        "Performs conservative ingredient consistency analysis using exact "
        "canonical names and approved aliases. This is not food fraud or "
        "adulteration detection."
    ),
)
def check_recipe_consistency(
    payload: RecipeConsistencyRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RecipeConsistencyResponse:
    recipe = db.scalars(
        select(Recipe)
        .options(selectinload(Recipe.ingredients))
        .where(
            Recipe.id == payload.recipe_id,
            or_(
                Recipe.user_id == user.id,
                Recipe.user_id.is_(None),
            ),
        )
    ).unique().first()

    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    result = analyze_recipe_consistency(
        db=db,
        recipe=recipe,
        supplied_ingredients=payload.supplied_ingredients,
    )

    return RecipeConsistencyResponse.model_validate(result)
