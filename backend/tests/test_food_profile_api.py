from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
from backend.app.models.user_food_profile import UserFoodProfile


@pytest.fixture
def food_profile_api():
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
            email="food-profile-owner@example.test",
            display_name="Food Profile Owner",
            password_hash="test-hash",
            is_active=True,
        )
        other = User(
            email="food-profile-other@example.test",
            display_name="Other User",
            password_hash="test-hash",
            is_active=True,
        )
        db.add_all([owner, other])
        db.flush()

        peanut = Food(
            name="Peanut",
            normalized_name="peanut",
            source="test",
        )
        chicken = Food(
            name="Chicken",
            normalized_name="chicken",
            source="test",
        )
        db.add_all([peanut, chicken])
        db.flush()

        mapped_allergen = Recipe(
            user_id=owner.id,
            name="Mapped Peanut Recipe",
            servings=1,
            source="test",
            source_metadata={},
        )
        unmapped_allergen = Recipe(
            user_id=owner.id,
            name="Unmapped Peanut Recipe",
            servings=1,
            source="test",
            source_metadata={},
        )
        vegetarian_conflict = Recipe(
            user_id=owner.id,
            name="Chicken Recipe",
            servings=1,
            source="test",
            source_metadata={},
        )
        unknown_ingredient = Recipe(
            user_id=owner.id,
            name="Unknown Ingredient Recipe",
            servings=1,
            source="test",
            source_metadata={},
        )
        empty_recipe = Recipe(
            user_id=owner.id,
            name="Empty Recipe",
            servings=1,
            source="test",
            source_metadata={},
        )
        private_recipe = Recipe(
            user_id=other.id,
            name="Private Recipe",
            servings=1,
            source="test",
            source_metadata={},
        )

        db.add_all([
            mapped_allergen,
            unmapped_allergen,
            vegetarian_conflict,
            unknown_ingredient,
            empty_recipe,
            private_recipe,
        ])
        db.flush()

        db.add_all([
            RecipeIngredient(
                recipe_id=mapped_allergen.id,
                food_id=peanut.id,
                ingredient_name="Peanut",
                mapping_status="exact_name",
            ),
            RecipeIngredient(
                recipe_id=unmapped_allergen.id,
                food_id=None,
                ingredient_name="Peanut",
                mapping_status="unmapped",
            ),
            RecipeIngredient(
                recipe_id=vegetarian_conflict.id,
                food_id=chicken.id,
                ingredient_name="Chicken",
                mapping_status="approved_alias",
            ),
            RecipeIngredient(
                recipe_id=unknown_ingredient.id,
                food_id=None,
                ingredient_name="Unidentified sauce",
                mapping_status="unmapped",
            ),
            RecipeIngredient(
                recipe_id=private_recipe.id,
                food_id=peanut.id,
                ingredient_name="Peanut",
                mapping_status="exact_name",
            ),
        ])

        profile = UserFoodProfile(
            user_id=owner.id,
            allergies=[{"name": "peanut", "severity": "severe"}],
            intolerances=[],
            dietary_preferences=["vegetarian"],
            goals=[],
            disliked_foods=[],
            cuisine_interests=[],
        )
        db.add(profile)
        db.commit()

        ids = {
            "mapped_allergen": mapped_allergen.id,
            "unmapped_allergen": unmapped_allergen.id,
            "vegetarian_conflict": vegetarian_conflict.id,
            "unknown_ingredient": unknown_ingredient.id,
            "empty_recipe": empty_recipe.id,
            "private_recipe": private_recipe.id,
        }

    client = TestClient(app)

    yield SimpleNamespace(
        client=client,
        ids=ids,
        factory=factory,
    )

    client.close()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
    Base.metadata.drop_all(engine)
    engine.dispose()


def assess_recipe(harness, recipe_key):
    recipe_id = harness.ids[recipe_key]
    return harness.client.get(
        f"/api/v1/food-profile/recipes/{recipe_id}/assess"
    )


def test_mapped_allergen_is_reported_as_ingredient_list_conflict(
    food_profile_api,
):
    response = assess_recipe(food_profile_api, "mapped_allergen")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "allergy_conflict"
    assert data["safe_to_assume"] is False
    assert data["unknown_ingredients"] == []
    assert any(
        match["concern_type"] == "allergy"
        and match["certainty"] == "ingredient_list"
        for match in data["matches"]
    )


def test_unmapped_allergen_is_possible_and_remains_unknown(
    food_profile_api,
):
    response = assess_recipe(food_profile_api, "unmapped_allergen")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "allergy_conflict"
    assert data["safe_to_assume"] is False
    assert data["unknown_ingredients"] == ["Peanut"]
    assert any(
        match["concern_type"] == "allergy"
        and match["certainty"] == "possible"
        for match in data["matches"]
    )


def test_mapped_chicken_conflicts_with_vegetarian_profile(
    food_profile_api,
):
    response = assess_recipe(food_profile_api, "vegetarian_conflict")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "preference_conflict"
    assert any(
        match["concern_type"] == "dietary_preference"
        and match["concern"] == "vegetarian"
        for match in data["matches"]
    )


def test_unmapped_non_conflicting_ingredient_requires_caution(
    food_profile_api,
):
    response = assess_recipe(food_profile_api, "unknown_ingredient")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "insufficient_evidence"
    assert data["safe_to_assume"] is False
    assert data["unknown_ingredients"] == ["Unidentified sauce"]


def test_missing_profile_never_assumes_safety(food_profile_api):
    with food_profile_api.factory() as db:
        profile = db.scalar(
            select(UserFoodProfile).where(UserFoodProfile.user_id == 1)
        )
        assert profile is not None
        db.delete(profile)
        db.commit()

    response = assess_recipe(food_profile_api, "mapped_allergen")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "profile_missing"
    assert data["safe_to_assume"] is False
    assert data["unknown_ingredients"] == ["Peanut"]
    assert data["matches"] == []


def test_recipe_without_ingredients_returns_422(food_profile_api):
    response = assess_recipe(food_profile_api, "empty_recipe")

    assert response.status_code == 422
    assert "no ingredient records" in response.json()["detail"].lower()


def test_private_recipe_owned_by_another_user_returns_404(
    food_profile_api,
):
    response = assess_recipe(food_profile_api, "private_recipe")

    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found."
