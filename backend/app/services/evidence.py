from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.evidence_document import EvidenceDocument
from backend.app.models.food import Food
from backend.app.models.recipe import Recipe
from backend.app.services.nutrition.nutrient_validation import nutrient_value_status


RECONCILABLE_SOURCE_TYPES = ("food", "nutrient", "shared_recipe")


def _canonical_hash(title: str, content: str, provenance: dict[str, Any]) -> str:
    payload = json.dumps(
        {"title": title, "content": content, "provenance": provenance},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _upsert(
    db: Session,
    *,
    source_type: str,
    source_id: str,
    title: str,
    content: str,
    provenance: dict[str, Any],
) -> str:
    content_hash = _canonical_hash(title, content, provenance)
    document = db.scalar(
        select(EvidenceDocument).where(
            EvidenceDocument.source_type == source_type,
            EvidenceDocument.source_id == source_id,
        )
    )

    if document is None:
        db.add(
            EvidenceDocument(
                source_type=source_type,
                source_id=source_id,
                title=title,
                content=content,
                provenance=provenance,
                content_hash=content_hash,
                status="pending",
            )
        )
        return "created"

    if document.content_hash == content_hash:
        if document.status == "stale":
            document.status = "pending"
            return "reactivated"
        return "unchanged"

    document.title = title
    document.content = content
    document.provenance = provenance
    document.content_hash = content_hash
    document.status = "pending"
    return "updated"


def _food_documents(food: Food) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []

    food_provenance = {
        "source": food.source,
        "external_id": food.external_id,
        "source_url": food.source_url,
        "category": food.category,
        "record_type": "food_catalog",
    }

    food_content = "\n".join(
        part
        for part in (
            f"Food: {food.name}",
            f"Category: {food.category}" if food.category else None,
            f"Description: {food.description}" if food.description else None,
            f"Normalized name: {food.normalized_name}",
            f"Catalog source: {food.source}",
        )
        if part
    )

    documents.append({
        "source_type": "food",
        "source_id": str(food.id),
        "title": food.name,
        "content": food_content,
        "provenance": food_provenance,
    })

    for nutrient in food.nutrients:
        if nutrient_value_status(nutrient.amount, nutrient.basis_g) != "valid":
            continue

        amount = Decimal(str(nutrient.amount))
        basis = Decimal(str(nutrient.basis_g))
        title = f"{nutrient.display_name} in {food.name}"

        content = (
            f"Food: {food.name}\n"
            f"Nutrient: {nutrient.display_name}\n"
            f"Amount: {amount} {nutrient.unit}\n"
            f"Measurement basis: per {basis} g\n"
            f"Source: {nutrient.source}\n"
            f"Derivation: {nutrient.derivation_description or 'Unavailable'}\n"
            f"Derivation source: {nutrient.derivation_source_description or 'Unavailable'}"
        )

        provenance = {
            "record_type": "food_nutrient",
            "food_id": food.id,
            "food_name": food.name,
            "nutrient_key": nutrient.nutrient_key,
            "source": nutrient.source,
            "source_nutrient_id": nutrient.source_nutrient_id,
            "derivation_code": nutrient.derivation_code,
            "derivation_description": nutrient.derivation_description,
            "derivation_source_description": nutrient.derivation_source_description,
            "amount": str(amount),
            "unit": nutrient.unit,
            "basis_g": str(basis),
        }

        documents.append({
            "source_type": "nutrient",
            "source_id": f"{food.id}:{nutrient.nutrient_key}",
            "title": title,
            "content": content,
            "provenance": provenance,
        })

    return documents


def _shared_recipe_document(recipe: Recipe) -> dict[str, Any]:
    ingredient_lines = [
        (
            f"- {item.ingredient_name}: {item.quantity} {item.unit}"
            + (f" (food_id: {item.food_id})" if item.food_id is not None else "")
        )
        for item in recipe.ingredients
    ]

    content_parts = [
        f"Recipe: {recipe.name}",
        f"Servings: {recipe.servings}",
        "Ingredients:",
        *(ingredient_lines or ["- No ingredients recorded"]),
    ]

    if recipe.instructions:
        content_parts.extend(["Instructions:", recipe.instructions])

    provenance = {
        "record_type": "shared_recipe",
        "recipe_id": recipe.id,
        "owner_scope": "shared",
        "servings": recipe.servings,
        "ingredient_count": len(recipe.ingredients),
        "ingredient_food_ids": sorted(
            {item.food_id for item in recipe.ingredients if item.food_id is not None}
        ),
    }

    return {
        "source_type": "shared_recipe",
        "source_id": str(recipe.id),
        "title": recipe.name,
        "content": "\n".join(content_parts),
        "provenance": provenance,
    }


def _reconcile_stale_documents(
    db: Session,
    active_sources: set[tuple[str, str]],
) -> int:
    """Mark obsolete catalog/shared evidence stale without deleting history."""
    documents = db.scalars(
        select(EvidenceDocument).where(
            EvidenceDocument.source_type.in_(RECONCILABLE_SOURCE_TYPES)
        )
    ).all()

    stale_count = 0

    for document in documents:
        source_key = (document.source_type, document.source_id)

        if source_key not in active_sources and document.status != "stale":
            document.status = "stale"
            stale_count += 1

    return stale_count


def sync_evidence_documents(db: Session) -> dict[str, int]:
    """Synchronize eligible global evidence and reconcile obsolete records.

    Private recipes, diaries and user profiles are never globally indexed.
    The caller controls the transaction and must commit or roll back.
    """
    counts = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "reactivated": 0,
        "stale": 0,
    }

    active_sources: set[tuple[str, str]] = set()

    foods = db.scalars(
        select(Food)
        .options(selectinload(Food.nutrients))
        .order_by(Food.id.asc())
    ).unique().all()

    for food in foods:
        for document in _food_documents(food):
            active_sources.add(
                (document["source_type"], document["source_id"])
            )
            outcome = _upsert(db, **document)
            counts[outcome] += 1

    shared_recipes = db.scalars(
        select(Recipe)
        .options(selectinload(Recipe.ingredients))
        .where(Recipe.user_id.is_(None))
        .order_by(Recipe.id.asc())
    ).unique().all()

    for recipe in shared_recipes:
        document = _shared_recipe_document(recipe)
        active_sources.add(
            (document["source_type"], document["source_id"])
        )
        outcome = _upsert(db, **document)
        counts[outcome] += 1

    counts["stale"] = _reconcile_stale_documents(db, active_sources)

    db.flush()
    counts["total_processed"] = sum(counts.values())
    return counts
