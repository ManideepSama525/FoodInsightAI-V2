from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models  # noqa: F401
from backend.app.core.auth import get_current_user
from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.food import Food
from backend.app.models.recipe import Recipe, RecipeIngredient
from backend.app.models.user import User


@pytest.fixture
def food_auth_api():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    previous = app.dependency_overrides.copy()

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        is_active=True,
    )

    with factory() as db:
        owner = User(
            email="owner@example.test",
            display_name="Owner",
            password_hash="test-hash",
            is_active=True,
        )
        other = User(
            email="other@example.test",
            display_name="Other",
            password_hash="test-hash",
            is_active=True,
        )
        db.add_all([owner, other])
        db.flush()

        rice = Food(
            name="Rice",
            normalized_name="rice",
            source="test",
        )
        milk = Food(
            name="Milk",
            normalized_name="milk",
            source="test",
        )
        tomato = Food(
            name="Tomato",
            normalized_name="tomato",
            source="test",
        )
        db.add_all([rice, milk, tomato])
        db.flush()

        own_recipe = Recipe(
            user_id=owner.id,
            name="Rice and Milk",
            servings=2,
            source="test",
            source_metadata={},
        )
        private_recipe = Recipe(
            user_id=other.id,
            name="Other User Private Recipe",
            servings=2,
            source="test",
            source_metadata={},
        )
        shared_recipe = Recipe(
            user_id=None,
            name="Shared Rice Recipe",
            servings=1,
            source="test",
            source_metadata={},
        )
        db.add_all([own_recipe, private_recipe, shared_recipe])
        db.flush()

        db.add_all([
            RecipeIngredient(
                recipe_id=own_recipe.id,
                food_id=rice.id,
                ingredient_name="Rice",
            ),
            RecipeIngredient(
                recipe_id=own_recipe.id,
                food_id=milk.id,
                ingredient_name="Milk",
            ),
            RecipeIngredient(
                recipe_id=shared_recipe.id,
                food_id=rice.id,
                ingredient_name="Rice",
            ),
        ])
        db.commit()

        ids = {
            "own_recipe": own_recipe.id,
            "private_recipe": private_recipe.id,
            "shared_recipe": shared_recipe.id,
        }

    client = TestClient(app)

    yield SimpleNamespace(client=client, ids=ids)

    client.close()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
    Base.metadata.drop_all(engine)
    engine.dispose()


def post_consistency(harness, recipe_id, ingredients):
    return harness.client.post(
        "/api/v1/food-authenticity/recipe-consistency",
        json={
            "recipe_id": recipe_id,
            "supplied_ingredients": ingredients,
        },
    )


def test_recipe_consistency_reports_missing_and_unexpected_ingredients(
    food_auth_api,
):
    response = post_consistency(
        food_auth_api,
        food_auth_api.ids["own_recipe"],
        ["Rice", "Tomato"],
    )

    assert response.status_code == 200
    body = response.json()

    assert body["analysis_type"] == "RECIPE_INGREDIENT_CONSISTENCY"
    assert body["status"] == "DISCREPANCIES_FOUND"
    assert body["counts"] == {
        "matched": 1,
        "missing": 1,
        "unexpected": 1,
        "unresolved_recipe": 0,
        "unresolved_supplied": 0,
    }
    assert body["matched_ingredients"][0]["canonical_name"] == "Rice"
    assert body["missing_expected_ingredients"][0]["canonical_name"] == "Milk"
    assert body["unexpected_supplied_ingredients"][0]["canonical_name"] == "Tomato"
    assert "do not prove" in body["disclaimer"]


def test_shared_recipe_is_visible(food_auth_api):
    response = post_consistency(
        food_auth_api,
        food_auth_api.ids["shared_recipe"],
        ["Rice"],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CONSISTENT"


def test_private_recipe_of_another_user_returns_404(food_auth_api):
    response = post_consistency(
        food_auth_api,
        food_auth_api.ids["private_recipe"],
        ["Rice"],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found."


def test_unknown_recipe_returns_404(food_auth_api):
    response = post_consistency(food_auth_api, 999999, ["Rice"])

    assert response.status_code == 404


def test_unauthenticated_request_returns_401(food_auth_api):
    app.dependency_overrides.pop(get_current_user, None)

    response = post_consistency(
        food_auth_api,
        food_auth_api.ids["own_recipe"],
        ["Rice"],
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"recipe_id": 1, "supplied_ingredients": []},
        {"recipe_id": 1, "supplied_ingredients": ["   "]},
        {"recipe_id": 1, "supplied_ingredients": ["x" * 241]},
        {"recipe_id": 0, "supplied_ingredients": ["Rice"]},
        {"recipe_id": 1, "supplied_ingredients": ["Rice"] * 101},
    ],
)
def test_invalid_request_is_rejected(food_auth_api, payload):
    response = food_auth_api.client.post(
        "/api/v1/food-authenticity/recipe-consistency",
        json=payload,
    )

    assert response.status_code == 422
