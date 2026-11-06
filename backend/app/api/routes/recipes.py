from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.models.food import Food
from backend.app.models.recipe import Recipe, RecipeIngredient
from backend.app.models.user import User
from backend.app.schemas.recipes import RecipeCreate, RecipeRead
from backend.app.services.nutrition.calculator import aggregate_recipe_nutrition

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _visible_recipe_filter(user_id: int):
    # NULL ownership is reserved for legacy shared recipes.
    return or_(Recipe.user_id == user_id, Recipe.user_id.is_(None))


def _serialize(recipe: Recipe, db: Session) -> RecipeRead:
    foods = {}
    ids = [item.food_id for item in recipe.ingredients if item.food_id is not None]
    if ids:
        foods = {
            food.id: food
            for food in db.scalars(
                select(Food)
                .options(selectinload(Food.nutrients))
                .where(Food.id.in_(ids))
            ).unique().all()
        }

    pairs = [
        (foods[item.food_id], item.quantity)
        for item in recipe.ingredients
        if item.food_id in foods
    ]
    per_recipe = aggregate_recipe_nutrition(pairs)
    per_serving = []
    divisor = Decimal(recipe.servings)

    for nutrient in per_recipe:
        per_serving.append({
            **nutrient,
            "amount": (
                None
                if nutrient["amount"] is None
                else (nutrient["amount"] / divisor).quantize(Decimal("0.01"))
            ),
        })

    return RecipeRead(
        id=recipe.id,
        name=recipe.name,
        servings=recipe.servings,
        instructions=recipe.instructions,
        ingredients=recipe.ingredients,
        nutrition_per_recipe=per_recipe,
        nutrition_per_serving=per_serving,
    )


@router.post("", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
def create_recipe(
    payload: RecipeCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RecipeRead:
    ids = {item.food_id for item in payload.ingredients}
    foods = {
        food.id: food
        for food in db.scalars(select(Food).where(Food.id.in_(ids))).all()
    }
    missing = ids - foods.keys()

    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Food records not found: {sorted(missing)}",
        )

    recipe = Recipe(
        user_id=user.id,
        name=payload.name.strip(),
        servings=payload.servings,
        instructions=payload.instructions,
    )
    recipe.ingredients = [
        RecipeIngredient(
            food_id=item.food_id,
            ingredient_name=foods[item.food_id].name,
            quantity=item.quantity_g,
            unit="g",
        )
        for item in payload.ingredients
    ]

    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return _serialize(recipe, db)


@router.get("", response_model=list[RecipeRead])
def list_recipes(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=50),
) -> list[RecipeRead]:
    recipes = db.scalars(
        select(Recipe)
        .options(selectinload(Recipe.ingredients))
        .where(_visible_recipe_filter(user.id))
        .order_by(Recipe.id.desc())
        .limit(limit)
    ).unique().all()

    return [_serialize(recipe, db) for recipe in recipes]


@router.get("/{recipe_id}", response_model=RecipeRead)
def get_recipe(
    recipe_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RecipeRead:
    recipe = db.scalars(
        select(Recipe)
        .options(selectinload(Recipe.ingredients))
        .where(
            Recipe.id == recipe_id,
            _visible_recipe_filter(user.id),
        )
    ).unique().first()

    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    return _serialize(recipe, db)