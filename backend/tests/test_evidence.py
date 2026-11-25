from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.models import EvidenceDocument, Food, FoodNutrient, Recipe, RecipeIngredient
from backend.app.services.evidence import sync_evidence_documents


def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_sync_creates_food_nutrient_and_only_shared_recipe_evidence():
    engine, db = make_session()
    try:
        food = Food(
            name="Cooked rice",
            normalized_name="cooked rice",
            category="Grains",
            source="test_catalog",
            external_id="rice-1",
            description="Cooked white rice",
        )
        food.nutrients = [
            FoodNutrient(
                nutrient_key="protein",
                display_name="Protein",
                amount=Decimal("2.50"),
                unit="g",
                basis_g=Decimal("100"),
                source="test_nutrition",
                source_nutrient_id="P1",
                derivation_code="A",
                derivation_description="Analytical",
                derivation_source_description="Analytical data",
            ),
            FoodNutrient(
                nutrient_key="unknown",
                display_name="Unknown nutrient",
                amount=None,
                unit="mg",
                basis_g=Decimal("100"),
                source="test_nutrition",
            ),
        ]
        shared = Recipe(
            user_id=None,
            name="Shared rice bowl",
            servings=2,
            instructions="Serve warm",
            ingredients=[
                RecipeIngredient(
                    ingredient_name="Cooked rice",
                    food_id=None,
                    quantity=Decimal("200"),
                    unit="g",
                )
            ],
        )
        private = Recipe(
            user_id=123,
            name="Private family recipe",
            servings=1,
            instructions="Private instructions",
            ingredients=[
                RecipeIngredient(
                    ingredient_name="Cooked rice",
                    food_id=None,
                    quantity=Decimal("100"),
                    unit="g",
                )
            ],
        )
        db.add_all([food, shared, private])
        db.commit()

        result = sync_evidence_documents(db)
        db.commit()

        documents = db.scalars(select(EvidenceDocument)).all()
        keys = {(item.source_type, item.source_id) for item in documents}

        assert result["created"] == 3
        assert result["updated"] == 0
        assert result["unchanged"] == 0
        assert ("food", str(food.id)) in keys
        assert ("nutrient", f"{food.id}:protein") in keys
        assert ("shared_recipe", str(shared.id)) in keys
        assert ("nutrient", f"{food.id}:unknown") not in keys
        assert ("shared_recipe", str(private.id)) not in keys
        assert all("Private family recipe" not in item.title for item in documents)

        nutrient_doc = next(
            item for item in documents
            if item.source_type == "nutrient"
            and item.source_id == f"{food.id}:protein"
        )
        assert nutrient_doc.provenance["derivation_code"] == "A"
        assert nutrient_doc.provenance["derivation_description"] == "Analytical"
        assert nutrient_doc.provenance["derivation_source_description"] == "Analytical data"
        assert "Analytical" in nutrient_doc.content
    finally:
        db.close()
        engine.dispose()


def test_sync_is_idempotent_and_does_not_rewrite_unchanged_evidence():
    engine, db = make_session()
    try:
        db.add(
            Food(
                name="Oats",
                normalized_name="oats",
                category="Grains",
                source="test_catalog",
                description="Rolled oats",
            )
        )
        db.commit()

        first = sync_evidence_documents(db)
        db.commit()
        original = db.scalar(
            select(EvidenceDocument).where(EvidenceDocument.source_type == "food")
        )
        original_hash = original.content_hash
        original_id = original.id

        second = sync_evidence_documents(db)
        db.commit()
        current = db.scalar(
            select(EvidenceDocument).where(EvidenceDocument.source_type == "food")
        )

        assert first["created"] == 1
        assert second["created"] == 0
        assert second["updated"] == 0
        assert second["unchanged"] == 1
        assert current.id == original_id
        assert current.content_hash == original_hash
    finally:
        db.close()
        engine.dispose()


def test_sync_updates_changed_source_and_marks_it_pending():
    engine, db = make_session()
    try:
        food = Food(
            name="Apple",
            normalized_name="apple",
            category="Fruit",
            source="test_catalog",
            description="Fresh apple",
        )
        db.add(food)
        db.commit()

        sync_evidence_documents(db)
        db.commit()

        document = db.scalar(
            select(EvidenceDocument).where(EvidenceDocument.source_type == "food")
        )
        document.status = "indexed"
        old_hash = document.content_hash

        food.description = "Fresh red apple"
        db.commit()

        result = sync_evidence_documents(db)
        db.commit()

        assert result["updated"] == 1
        assert document.content_hash != old_hash
        assert document.status == "pending"
        assert "Fresh red apple" in document.content
    finally:
        db.close()
        engine.dispose()






def test_reconciliation_marks_deleted_sources_and_private_recipes_stale():
    engine, db = make_session()
    try:
        deleted_food = Food(
            name="Old food",
            normalized_name="old food",
            category="Test",
            source="test_catalog",
        )

        active_food = Food(
            name="Rice",
            normalized_name="rice",
            category="Grains",
            source="test_catalog",
            nutrients=[
                FoodNutrient(
                    nutrient_key="protein",
                    display_name="Protein",
                    amount=Decimal("2.5"),
                    unit="g",
                    basis_g=Decimal("100"),
                    source="test_nutrition",
                )
            ],
        )

        shared = Recipe(
            user_id=None,
            name="Previously shared recipe",
            servings=2,
            instructions="Serve warm",
        )

        db.add_all([deleted_food, active_food, shared])
        db.commit()

        sync_evidence_documents(db)
        db.commit()

        deleted_food_id = str(deleted_food.id)
        nutrient_id = f"{active_food.id}:protein"
        recipe_id = str(shared.id)

        nutrient = active_food.nutrients[0]

        db.delete(deleted_food)
        db.delete(nutrient)
        shared.user_id = 123
        db.commit()

        result = sync_evidence_documents(db)
        db.commit()

        assert result["stale"] == 3

        stale_documents = db.scalars(
            select(EvidenceDocument).where(
                EvidenceDocument.status == "stale"
            )
        ).all()

        stale_keys = {
            (item.source_type, item.source_id)
            for item in stale_documents
        }

        assert ("food", deleted_food_id) in stale_keys
        assert ("nutrient", nutrient_id) in stale_keys
        assert ("shared_recipe", recipe_id) in stale_keys

        # A subsequent reconciliation must not repeatedly change stale rows.
        second = sync_evidence_documents(db)
        db.commit()

        assert second["stale"] == 0

        # Private recipe content remains excluded.
        assert not any(
            item.source_type == "shared_recipe"
            and item.source_id == recipe_id
            and item.status != "stale"
            for item in db.scalars(select(EvidenceDocument)).all()
        )
    finally:
        db.close()
        engine.dispose()


def test_stale_evidence_is_reactivated_as_pending():
    engine, db = make_session()
    try:
        food = Food(
            name="Banana",
            normalized_name="banana",
            category="Fruit",
            source="test_catalog",
        )
        db.add(food)
        db.commit()

        sync_evidence_documents(db)
        db.commit()

        document = db.scalar(
            select(EvidenceDocument).where(
                EvidenceDocument.source_type == "food",
                EvidenceDocument.source_id == str(food.id),
            )
        )

        original_id = document.id
        original_hash = document.content_hash
        document.status = "stale"
        db.commit()

        result = sync_evidence_documents(db)
        db.commit()

        current = db.get(EvidenceDocument, original_id)

        assert result["reactivated"] == 1
        assert current.id == original_id
        assert current.status == "pending"
        assert current.content_hash == original_hash
    finally:
        db.close()
        engine.dispose()


def test_reconciliation_does_not_mark_unrelated_evidence_types_stale():
    engine, db = make_session()
    try:
        unrelated = EvidenceDocument(
            source_type="external_reference",
            source_id="external-1",
            title="External reference",
            content="Unrelated evidence",
            provenance={"record_type": "external"},
            content_hash="a" * 64,
            status="indexed",
        )
        db.add(unrelated)
        db.commit()

        result = sync_evidence_documents(db)
        db.commit()

        assert result["stale"] == 0
        assert unrelated.status == "indexed"
    finally:
        db.close()
        engine.dispose()