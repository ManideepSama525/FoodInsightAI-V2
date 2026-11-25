from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.evidence_document import EvidenceDocument
from backend.app.models.food import Food
from backend.app.services.evidence_analysis import (
    aggregate_evidence,
    assess_provenance_quality,
    detect_source_conflicts,
)
from backend.app.services.knowledge_graph import knowledge_graph
from backend.app.services.vector_evidence import search_evidence
from backend.app.services.regulatory_assessment import (is_current_regulatory_evidence,)

ALLOWED_SOURCE_TYPES = ("food", "nutrient", "shared_recipe", "regulatory")
RRF_K = 60

QUERY_STOP_WORDS = {
    "what", "are", "is", "in", "the", "of", "and", "for",
    "does", "do", "how", "many", "much", "per", "with",
    "on", "to", "a", "an", "tell", "me", "about",
    "present", "there", "which", "that", "this", "show",
    "give", "list", "can", "you", "please",
    "content", "amount", "value", "contains", "contain",
}


def _tokens(query: str) -> list[str]:
    return list(dict.fromkeys(
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) >= 2 and token not in QUERY_STOP_WORDS
    ))


GENERAL_NUTRITION_TERMS = {
    "nutrients", "nutrition", "nutritional", "macros",
}

NUTRIENT_QUERY_ALIASES = {
    "energy_kcal": {"energy", "calorie", "calories", "kcal"},
    "protein": {"protein"},
    "total_carbohydrate": {"carbohydrate", "carbohydrates", "carb", "carbs", "total"},
    "total_fat": {"fat", "fats", "total", "totalfat"},
    "fiber": {"fiber", "fibre"},
    "sodium": {"sodium"},
    "cholesterol": {"cholesterol"},
    "saturated_fat": {"saturated", "fat", "saturatedfat"},
    "sugar": {"sugar", "sugars"},
}

GENERAL_NUTRITION_QUERY_TERMS = GENERAL_NUTRITION_TERMS


def _food_query_terms(terms: list[str]) -> list[str]:
    """Remove nutrient intent and generic nutrition wording from food terms."""
    nutrient_terms = set().union(*NUTRIENT_QUERY_ALIASES.values())
    return [
        term for term in terms
        if term not in nutrient_terms
        and term not in GENERAL_NUTRITION_QUERY_TERMS
    ]


def _food_anchor_ids(foods: list[Any], terms: list[str]) -> set[str]:
    """Match the complete food phrase, not an arbitrary shared token."""
    food_terms = _food_query_terms(terms)
    if not food_terms:
        return set()

    anchors: set[str] = set()
    for food in foods:
        names = (
            food.name or "",
            food.normalized_name or "",
        )
        matched = False
        for name in names:
            name_tokens = re.findall(r"[a-z0-9]+", name.lower())
            width = len(food_terms)
            if any(
                name_tokens[index:index + width] == food_terms
                for index in range(len(name_tokens) - width + 1)
            ):
                matched = True
                break
        if matched:
            anchors.add(str(food.id))
    return anchors


def _filter_candidates_to_food_anchors(
    candidates: dict[tuple[str, str], dict[str, Any]],
    anchor_ids: set[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Keep evidence for explicitly requested foods, preserving shared recipes."""
    if not anchor_ids:
        return candidates

    filtered = {}

    for key, item in candidates.items():
        source_type = item.get("source_type")
        source_id = str(item.get("source_id", ""))

        if source_type in ("shared_recipe", "regulatory"):
            filtered[key] = item
            continue

        if source_type == "food":
            if source_id in anchor_ids:
                filtered[key] = item
            continue

        if source_type == "nutrient":
            records = item.get("provenance_records") or [
                item.get("provenance") or {}
            ]
            evidence_food_ids = {
                str(record["food_id"])
                for record in records
                if record.get("food_id") is not None
            }

            if not evidence_food_ids and ":" in source_id:
                evidence_food_ids.add(source_id.split(":", 1)[0])

            if evidence_food_ids.intersection(anchor_ids):
                filtered[key] = item

    return filtered


def _eligible_recipe(item: dict[str, Any]) -> bool:
    if item.get("source_type") != "shared_recipe":
        return True
    return item.get("provenance", {}).get("owner_scope") == "shared"


def _merge_candidate(
    candidates: dict[tuple[str, str], dict[str, Any]],
    item: dict[str, Any],
    channel: str,
    rank: int,
) -> None:
    source_type = item.get("source_type")
    source_id = str(item.get("source_id", ""))

    if source_type not in ALLOWED_SOURCE_TYPES or not source_id:
        return
    if not _eligible_recipe(item):
        return
    if source_type == "regulatory":
        provenance = item.get("provenance") or {}
        required = (
            "authority",
            "jurisdiction",
            "source_url",
            "document_type",
            "document_status",
            "published_at",
            "last_checked_at",
        )
        if (
            not all(provenance.get(key) for key in required)
            or not is_current_regulatory_evidence(provenance)
        ):
            return

    key = (source_type, source_id)
    candidate = candidates.setdefault(key, {
        "source_type": source_type,
        "source_id": source_id,
        "title": item.get("title", ""),
        "content": item.get("content", ""),
        "provenance": item.get("provenance") or {},
        "provenance_records": (
            [dict(item["provenance"])]
            if item.get("provenance")
            else []
        ),
        "content_hash": item.get("content_hash"),
        "retrieval_sources": [],
        "rank_score": 0.0,
        "source_ranks": {},
        "similarity_score": None,
    })

    incoming_provenance = item.get("provenance") or {}
    if incoming_provenance:
        provenance_key = json.dumps(
            incoming_provenance, sort_keys=True, default=str
        )
        existing_keys = {
            json.dumps(record, sort_keys=True, default=str)
            for record in candidate["provenance_records"]
        }
        if provenance_key not in existing_keys:
            candidate["provenance_records"].append(dict(incoming_provenance))

    if channel not in candidate["retrieval_sources"]:
        candidate["retrieval_sources"].append(channel)

    candidate["source_ranks"][channel] = rank
    candidate["rank_score"] += 1.0 / (RRF_K + rank)

    # Prefer source-attributed SQL evidence when merging graph/vector results.
    if not candidate["title"] and item.get("title"):
        candidate["title"] = item["title"]
    if not candidate["content"] and item.get("content"):
        candidate["content"] = item["content"]
    if not candidate["provenance"] and item.get("provenance"):
        candidate["provenance"] = item["provenance"]
    if not candidate["content_hash"] and item.get("content_hash"):
        candidate["content_hash"] = item["content_hash"]

    score = item.get("score")
    if score is not None:
        candidate["similarity_score"] = float(score)



PRIMARY_NUTRIENT_ORDER = {
    "energy_kcal": 0,
    "protein": 1,
    "total_carbohydrate": 2,
    "total_fat": 3,
    "fiber": 4,
    "sodium": 5,
    "usda_1063": 6,
    "usda_1092": 7,
}

NUTRIENT_QUERY_PHRASES = {
    "energy_kcal": ("calories", "calorie", "kcal", "energy"),
    "protein": ("protein",),
    "total_carbohydrate": ("carbohydrates", "carbohydrate", "carbs", "carb"),
    "total_fat": ("total fat", "fat"),
    "fiber": ("fiber", "fibre"),
    "sodium": ("sodium",),
    "cholesterol": ("cholesterol",),
    "saturated_fat": ("saturated fat",),
    "sugar": ("sugars", "sugar"),
}


def _requested_nutrient_phrases(query: str) -> list[str]:
    """Return specific nutrient phrases present in the user's query."""
    normalized = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
    found = []
    for phrases in NUTRIENT_QUERY_PHRASES.values():
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", normalized):
                found.append(phrase)
    # Prefer longer phrases (e.g. saturated fat over the generic word fat).
    unique = set(found)
    return sorted(
        (
            phrase for phrase in unique
            if not any(
                phrase != other and re.search(
                    rf"\b{re.escape(phrase)}\b", other
                )
                for other in unique
            )
        ),
        key=lambda value: (-len(value.split()), -len(value)),
    )


def _rank_general_nutrition_results(
    results: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Prioritize the requested nutrient, or primary nutrients for broad queries."""
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    requested_phrases = _requested_nutrient_phrases(query)
    is_general_query = bool(query_terms.intersection(GENERAL_NUTRITION_TERMS))

    if not requested_phrases and not is_general_query:
        return results

    def nutrient_text(item: dict[str, Any], records: list[dict[str, Any]]) -> str:
        parts = [
            str(item.get("title") or ""),
            str(item.get("content") or ""),
        ]
        parts.extend(str(record.get("nutrient_key") or "") for record in records)
        return " ".join(parts).lower().replace("_", " ")

    def sort_key(item: dict[str, Any]) -> tuple:
        source_type = item.get("source_type")
        rank_score = -float(item.get("rank_score") or 0)

        if source_type == "food":
            return (2 if requested_phrases else 0, 0, rank_score)

        if source_type != "nutrient":
            return (3, 0, rank_score)

        records = item.get("provenance_records") or [
            item.get("provenance") or {}
        ]
        text = nutrient_text(item, records)

        requested_priority = next(
            (
                index for index, phrase in enumerate(requested_phrases)
                if re.search(rf"\b{re.escape(phrase)}\b", text)
            ),
            None,
        )

        if requested_priority is not None:
            return (0, requested_priority, rank_score)

        if requested_phrases:
            return (1, 0, rank_score)

        nutrient_keys = [
            str(record.get("nutrient_key") or "")
            for record in records
        ]
        priorities = [
            PRIMARY_NUTRIENT_ORDER[key]
            for key in nutrient_keys
            if key in PRIMARY_NUTRIENT_ORDER
        ]

        amounts = []
        for record in records:
            try:
                amounts.append(float(record.get("amount")))
            except (TypeError, ValueError):
                continue

        zero_penalty = 0 if any(amount > 0 for amount in amounts) else 1
        if priorities:
            return (1, min(priorities), zero_penalty, rank_score)
        return (2, 0, zero_penalty, rank_score)

    return sorted(results, key=sort_key)


def retrieve_hybrid_evidence(
    db: Session,
    query: str,
    *,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """Retrieve and fuse SQL, knowledge-graph and vector evidence.

    SQL evidence is source-attributed. Graph results provide relational
    context. Vector results provide semantic matches. RRF combines ranks
    without treating unlike similarity scores as calibrated probabilities.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query cannot be empty")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
        raise ValueError("top_k must be an integer between 1 and 50")

    terms = _tokens(query)
    if not terms:
        return []

    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    # 1. SQL evidence-document retrieval.
    conditions = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.extend([
            EvidenceDocument.title.ilike(pattern),
            EvidenceDocument.content.ilike(pattern),
        ])

    sql_documents = db.scalars(
        select(EvidenceDocument)
        .where(
            EvidenceDocument.status == "indexed",
            EvidenceDocument.source_type.in_(ALLOWED_SOURCE_TYPES),
            or_(*conditions),
        )
        .order_by(EvidenceDocument.id.asc())
        .limit(100)
    ).all()

    for rank, document in enumerate(sql_documents, start=1):
        _merge_candidate(candidates, {
            "source_type": document.source_type,
            "source_id": document.source_id,
            "title": document.title,
            "content": document.content,
            "provenance": document.provenance or {},
            "content_hash": document.content_hash,
        }, "sql", rank)

    # 2. SQL food-catalog matching, followed by graph neighborhood retrieval.
    food_terms = _food_query_terms(terms)
    food_conditions = []
    for term in food_terms:
        pattern = f"%{term}%"
        food_conditions.extend([
            Food.name.ilike(pattern),
            Food.normalized_name.ilike(pattern),
        ])

    foods = []
    if food_conditions:
        foods = db.scalars(
            select(Food)
            .options(selectinload(Food.nutrients))
            .where(or_(*food_conditions))
            .order_by(Food.name.asc())
        ).unique().all()

    anchor_ids = _food_anchor_ids(foods, terms)
    if anchor_ids:
        foods = [food for food in foods if str(food.id) in anchor_ids]

    for rank, food in enumerate(foods, start=1):
        provenance = {
            "source": food.source,
            "external_id": food.external_id,
            "source_url": food.source_url,
            "category": food.category,
            "record_type": "food_catalog",
        }
        _merge_candidate(candidates, {
            "source_type": "food",
            "source_id": str(food.id),
            "title": food.name,
            "content": food.description or food.name,
            "provenance": provenance,
        }, "sql_catalog", rank)

    if knowledge_graph.enabled:
        graph_rank = 0
        for food in foods[:10]:
            neighborhood = knowledge_graph.food_neighborhood(food.id)
            if not neighborhood:
                continue

            graph_food = neighborhood.get("food") or {}
            graph_rank += 1
            _merge_candidate(candidates, {
                "source_type": "food",
                "source_id": str(food.id),
                "title": graph_food.get("name") or food.name,
                "content": (
                    f"Food: {graph_food.get('name') or food.name}. "
                    "Relational food node found in the knowledge graph."
                ),
                "provenance": {
                    "record_type": "knowledge_graph_food",
                    "food_id": food.id,
                    "source": food.source,
                    "source_url": food.source_url,
                },
            }, "graph", graph_rank)

            for nutrient in neighborhood.get("nutrients", []):
                if not nutrient.get("key"):
                    continue

                graph_rank += 1
                source_id = f"{food.id}:{nutrient['key']}"
                amount = nutrient.get("amount")
                unit = nutrient.get("unit")
                basis = nutrient.get("basis_g")

                _merge_candidate(candidates, {
                    "source_type": "nutrient",
                    "source_id": source_id,
                    "title": f"{nutrient.get('name', nutrient['key'])} in {food.name}",
                    "content": (
                        f"Food: {food.name}\n"
                        f"Nutrient: {nutrient.get('name', nutrient['key'])}\n"
                        f"Amount: {amount} {unit}\n"
                        f"Measurement basis: per {basis} g\n"
                        f"Source: {nutrient.get('source') or food.source}\n"
                        f"Derivation: {nutrient.get('derivation_description') or 'Unavailable'}\n"
                        f"Derivation source: {nutrient.get('derivation_source_description') or 'Unavailable'}"
                    ),
                    "provenance": {
                        "record_type": "food_nutrient",
                        "food_id": food.id,
                        "food_name": food.name,
                        "nutrient_key": nutrient["key"],
                        "source": nutrient.get("source") or food.source,
                        "source_nutrient_id": nutrient.get("source_nutrient_id"),
                        "derivation_code": nutrient.get("derivation_code"),
                        "derivation_description": nutrient.get("derivation_description"),
                        "derivation_source_description": nutrient.get("derivation_source_description"),
                        "source_url": food.source_url,
                        "amount": str(amount) if amount is not None else None,
                        "unit": unit,
                        "basis_g": str(basis) if basis is not None else None,
                    },
                }, "graph", graph_rank)

    # 3. Semantic vector retrieval.
    vector_results = search_evidence(query, top_k=min(top_k * 3, 50))
    for rank, item in enumerate(vector_results, start=1):
        _merge_candidate(candidates, item, "vector", rank)

    # When the query names a catalog food, prevent unrelated foods
    # from entering the final result through weak lexical or vector matches.
    candidates = _filter_candidates_to_food_anchors(
        candidates, anchor_ids
    )

    # Aggregate candidates and retain all source attribution.
    results = aggregate_evidence(list(candidates.values()))

    # Compare every retained provenance record for nutrient disagreements.
    analysis = detect_source_conflicts(results)

    for item in results:
        item["source_conflicts"] = []
        item["incomparable_measurements"] = []
        item["invalid_measurements"] = []

        if item["source_type"] != "nutrient":
            continue

        provenance_records = item.get("provenance_records") or [
            item.get("provenance") or {}
        ]
        evidence_keys = {
            (str(record.get("food_id")), str(record.get("nutrient_key")))
            for record in provenance_records
            if record.get("food_id") is not None and record.get("nutrient_key")
        }

        item["source_conflicts"] = [
            record for record in analysis["conflicts"]
            if (record["food_id"], record["nutrient_key"]) in evidence_keys
        ]
        item["incomparable_measurements"] = [
            record for record in analysis["incomparable"]
            if (record["food_id"], record["nutrient_key"]) in evidence_keys
        ]
        item["invalid_measurements"] = [
            record for record in analysis["invalid_evidence"]
            if (str(record["food_id"]), record["nutrient_key"]) in evidence_keys
        ]

    # Assess provenance structure without inventing source reliability scores.
    for item in results:
        item["provenance_assessment"] = assess_provenance_quality(item)

    results = _rank_general_nutrition_results(results, query)
    return results[:top_k]
