import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every mapped model and foreign-key target before creating metadata.
from backend.app import models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.dish import Dish
from backend.app.models.food import RecognitionAlias
from backend.app.services.dish_recognition import (
    normalize_label,
    resolve_recognized_dish,
)


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


def add_dish(session, name, *, active=True):
    dish = Dish(
        name=name,
        normalized_name=name.casefold(),
        source="test",
        provenance={"fixture": True},
        is_active=active,
    )
    session.add(dish)
    session.flush()
    return dish


def add_alias(session, dish, label, *, model_source="any", active=True):
    alias = RecognitionAlias(
        dish_id=dish.id,
        food_id=None,
        label=label,
        normalized_label=normalize_label(label),
        model_source=model_source,
        source="test-curation",
        provenance="isolated test fixture",
        is_active=active,
    )
    session.add(alias)
    session.flush()
    return alias


def test_exact_model_alias_takes_priority_over_any_fallback(db_session):
    generic_dish = add_dish(db_session, "Generic Dish")
    indian_dish = add_dish(db_session, "Indian Dish")
    add_alias(db_session, generic_dish, "Idli", model_source="any")
    add_alias(db_session, indian_dish, "Idli", model_source="indian")
    db_session.commit()

    result = resolve_recognized_dish(db_session, "idli", "indian")

    assert result is not None
    assert result.id == indian_dish.id
    assert result.name == "Indian Dish"


def test_any_alias_is_used_when_no_exact_model_alias_exists(db_session):
    dish = add_dish(db_session, "Shared Dish")
    add_alias(db_session, dish, "Masala Dosa", model_source="any")
    db_session.commit()

    result = resolve_recognized_dish(db_session, "masala dosa", "food101")

    assert result is not None
    assert result.id == dish.id


def test_inactive_exact_alias_is_ignored_and_active_any_alias_can_fallback(
    db_session,
):
    fallback_dish = add_dish(db_session, "Fallback Dish")
    inactive_exact_dish = add_dish(db_session, "Inactive Exact Dish")
    add_alias(db_session, fallback_dish, "Pongal", model_source="any")
    add_alias(
        db_session,
        inactive_exact_dish,
        "Pongal",
        model_source="indian",
        active=False,
    )
    db_session.commit()

    result = resolve_recognized_dish(db_session, "Pongal", "indian")

    assert result is not None
    assert result.id == fallback_dish.id


def test_inactive_dish_is_not_returned(db_session):
    dish = add_dish(db_session, "Retired Dish", active=False)
    add_alias(db_session, dish, "Old Dish Label", model_source="food101")
    db_session.commit()

    assert resolve_recognized_dish(db_session, "Old Dish Label", "food101") is None


def test_unknown_and_empty_labels_return_none(db_session):
    dish = add_dish(db_session, "Known Dish")
    add_alias(db_session, dish, "Known Label", model_source="food101")
    db_session.commit()

    assert resolve_recognized_dish(db_session, "not registered", "food101") is None
    assert resolve_recognized_dish(db_session, "", "food101") is None
    assert resolve_recognized_dish(db_session, "   ", "food101") is None


def test_label_matching_normalizes_case_whitespace_and_unicode(db_session):
    dish = add_dish(db_session, "Unicode Dish")
    add_alias(
        db_session,
        dish,
        "  ＣＡＦÉ   DOSA ",
        model_source="food101",
    )
    db_session.commit()

    result = resolve_recognized_dish(
        db_session,
        "café\t  dosa",
        "food101",
    )

    assert result is not None
    assert result.id == dish.id


def test_normalize_label_uses_nfkc_casefold_and_collapsed_whitespace():
    assert normalize_label("  ＩＤＬＩ\t  Dosa  ") == "idli dosa"
    assert normalize_label("CAFÉ") == "café"
    assert normalize_label(" \n\t ") == ""
