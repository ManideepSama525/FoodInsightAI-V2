from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Import the model package so every mapped model and FK target is registered
# before Base.metadata.create_all() is called.
from backend.app import models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.dish import Dish, DishRecipe
from backend.app.models.recipe import Recipe, RecipeIngredient
from backend.app.services.dish_recognition import get_public_dish_recipes


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def add_recipe(session: Session, dish: Dish, name: str, *, user_id=None,
               association_active=True, source="test", ingredients=None):
    recipe = Recipe(
        user_id=user_id,
        name=name,
        servings=2,
        source=source,
        external_id=None,
        source_url=None,
        source_license=None,
        source_attribution="Isolated test fixture",
        source_metadata={},
    )
    session.add(recipe)
    session.flush()

    association = DishRecipe(
        dish_id=dish.id,
        recipe_id=recipe.id,
        source="test-curation",
        provenance={"test": True},
        is_active=association_active,
    )
    session.add(association)

    for item in ingredients or []:
        session.add(RecipeIngredient(recipe_id=recipe.id, **item))

    session.flush()
    return recipe


def make_dish(session):
    dish = Dish(
        name="Test Idli",
        normalized_name="test idli",
        source="test",
        provenance={"fixture": True},
        is_active=True,
    )
    session.add(dish)
    session.flush()
    return dish


def test_returns_public_recipes_and_excludes_private_recipes(db_session):
    dish = make_dish(db_session)
    public_recipe = add_recipe(db_session, dish, "Public Idli Recipe")
    private_recipe = add_recipe(
        db_session, dish, "Private Idli Recipe", user_id=987654
    )
    db_session.commit()

    results = get_public_dish_recipes(db_session, dish.id)

    assert [item["recipe_id"] for item in results] == [public_recipe.id]
    assert all(item["recipe_id"] != private_recipe.id for item in results)
    assert [item["recipe_name"] for item in results] == ["Public Idli Recipe"]


def test_excludes_inactive_dish_recipe_associations(db_session):
    dish = make_dish(db_session)
    active = add_recipe(db_session, dish, "Active Recipe")
    inactive = add_recipe(
        db_session, dish, "Inactive Recipe", association_active=False
    )
    db_session.commit()

    results = get_public_dish_recipes(db_session, dish.id)

    assert [item["recipe_id"] for item in results] == [active.id]
    assert inactive.id not in [item["recipe_id"] for item in results]


def test_preserves_ingredient_quantity_mapping_and_provenance_fields(db_session):
    dish = make_dish(db_session)
    recipe = add_recipe(
        db_session,
        dish,
        "Ingredient Detail Recipe",
        ingredients=[{
            "food_id": None,
            "ingredient_name": "Rice",
            "quantity": Decimal("1.250"),
            "unit": "cup",
            "raw_ingredient_text": "1 1/4 cups rice",
            "mapping_status": "unmapped",
            "quantity_status": "parsed",
        }],
    )
    db_session.commit()

    results = get_public_dish_recipes(db_session, dish.id)

    assert len(results) == 1
    result = results[0]
    assert result["recipe_id"] == recipe.id
    assert result["source_attribution"] == "Isolated test fixture"
    assert result["association_source"] == "test-curation"
    assert result["association_provenance"] == {"test": True}
    assert result["ingredients"] == [{
        "ingredient_name": "Rice",
        "food_id": None,
        "quantity": 1.25,
        "unit": "cup",
        "mapping_status": "unmapped",
        "quantity_status": "parsed",
    }]


def test_limits_public_recipe_results_to_five(db_session):
    dish = make_dish(db_session)
    for index in range(7):
        add_recipe(db_session, dish, f"Recipe {index:02d}")
    db_session.commit()

    results = get_public_dish_recipes(db_session, dish.id)

    assert len(results) == 5
    assert [item["recipe_name"] for item in results] == [
        "Recipe 00",
        "Recipe 01",
        "Recipe 02",
        "Recipe 03",
        "Recipe 04",
    ]


def test_unknown_dish_id_returns_empty_list(db_session):
    assert get_public_dish_recipes(db_session, 999999) == []
