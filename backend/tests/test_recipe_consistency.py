from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.food import Food
from backend.app.models.recipe import IngredientAlias, Recipe, RecipeIngredient
from backend.app.services.recipe_consistency import analyze_recipe_consistency


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine, factory()


def add_food(db, name, normalized_name=None):
    food = Food(
        name=name,
        normalized_name=normalized_name or name.lower(),
        source="test",
        external_id=None,
    )
    db.add(food)
    db.flush()
    return food


def add_recipe(db, ingredients):
    recipe = Recipe(
        name="Test Recipe",
        servings=2,
        source="test",
        source_metadata={},
    )
    db.add(recipe)
    db.flush()

    for ingredient in ingredients:
        db.add(RecipeIngredient(recipe_id=recipe.id, **ingredient))

    db.flush()
    return recipe


def test_exact_canonical_ingredient_matches():
    engine, db = make_session()
    try:
        rice = add_food(db, "Rice")
        recipe = add_recipe(db, [{
            "food_id": rice.id,
            "ingredient_name": "Rice",
            "quantity": None,
            "unit": None,
        }])

        result = analyze_recipe_consistency(db, recipe, ["Rice"])

        assert result["status"] == "CONSISTENT"
        assert result["counts"]["matched"] == 1
        assert result["counts"]["missing"] == 0
        assert result["counts"]["unexpected"] == 0
    finally:
        db.close()
        engine.dispose()


def test_approved_alias_resolves_to_canonical_food():
    engine, db = make_session()
    try:
        garlic = add_food(db, "Garlic, raw")
        db.add(IngredientAlias(
            alias="Garlic",
            normalized_alias="garlic",
            food_id=garlic.id,
            candidate_food_id=None,
            status="approved",
            source="test",
            provenance={},
        ))
        recipe = add_recipe(db, [{
            "food_id": garlic.id,
            "ingredient_name": "Garlic",
            "quantity": None,
            "unit": None,
        }])

        result = analyze_recipe_consistency(db, recipe, ["Garlic"])

        assert result["status"] == "CONSISTENT"
        assert result["counts"]["matched"] == 1
    finally:
        db.close()
        engine.dispose()


def test_missing_expected_ingredient_is_reported():
    engine, db = make_session()
    try:
        rice = add_food(db, "Rice")
        dal = add_food(db, "Lentils")
        recipe = add_recipe(db, [
            {
                "food_id": rice.id,
                "ingredient_name": "Rice",
                "quantity": None,
                "unit": None,
            },
            {
                "food_id": dal.id,
                "ingredient_name": "Lentils",
                "quantity": None,
                "unit": None,
            },
        ])

        result = analyze_recipe_consistency(db, recipe, ["Rice"])

        assert result["status"] == "DISCREPANCIES_FOUND"
        assert result["counts"]["missing"] == 1
        assert result["missing_expected_ingredients"][0]["canonical_name"] == "Lentils"
    finally:
        db.close()
        engine.dispose()


def test_unexpected_supplied_ingredient_is_reported():
    engine, db = make_session()
    try:
        rice = add_food(db, "Rice")
        potato = add_food(db, "Potato")
        recipe = add_recipe(db, [{
            "food_id": rice.id,
            "ingredient_name": "Rice",
            "quantity": None,
            "unit": None,
        }])

        result = analyze_recipe_consistency(db, recipe, ["Rice", "Potato"])

        assert result["status"] == "DISCREPANCIES_FOUND"
        assert result["counts"]["unexpected"] == 1
        assert result["unexpected_supplied_ingredients"][0]["canonical_name"] == "Potato"
    finally:
        db.close()
        engine.dispose()


def test_unapproved_alias_is_not_used():
    engine, db = make_session()
    try:
        garlic = add_food(db, "Garlic, raw")
        db.add(IngredientAlias(
            alias="Fresh Garlic",
            normalized_alias="fresh garlic",
            food_id=None,
            candidate_food_id=garlic.id,
            status="review_required",
            source="test",
            provenance={},
        ))
        recipe = add_recipe(db, [{
            "food_id": garlic.id,
            "ingredient_name": "Garlic, raw",
            "quantity": None,
            "unit": None,
        }])

        result = analyze_recipe_consistency(db, recipe, ["Fresh Garlic"])

        assert result["status"] == "REVIEW_REQUIRED"
        assert result["counts"]["unresolved_supplied"] == 1
        assert result["unresolved_supplied_ingredients"][0]["reason"] == (
            "NO_APPROVED_EXACT_MAPPING"
        )
    finally:
        db.close()
        engine.dispose()


def test_compound_ingredient_remains_unresolved():
    engine, db = make_session()
    try:
        rice = add_food(db, "Rice")
        recipe = add_recipe(db, [{
            "food_id": rice.id,
            "ingredient_name": "Rice",
            "quantity": None,
            "unit": None,
        }])

        result = analyze_recipe_consistency(
            db, recipe, ["Rice, finely chopped"]
        )

        assert result["status"] == "REVIEW_REQUIRED"
        assert result["counts"]["unresolved_supplied"] == 1
        assert result["unresolved_supplied_ingredients"][0]["reason"] == (
            "COMPOUND_OR_AMBIGUOUS_INGREDIENT"
        )
    finally:
        db.close()
        engine.dispose()


def test_existing_recipe_food_id_is_preserved():
    engine, db = make_session()
    try:
        rice = add_food(db, "Rice")
        recipe = add_recipe(db, [{
            "food_id": rice.id,
            "ingredient_name": "Stored Rice",
            "quantity": None,
            "unit": None,
        }])

        result = analyze_recipe_consistency(db, recipe, ["Rice"])

        assert result["counts"]["matched"] == 1
        assert result["matched_ingredients"][0]["reason"] == (
            "STORED_CANONICAL_FOOD_ID"
        )
    finally:
        db.close()
        engine.dispose()
