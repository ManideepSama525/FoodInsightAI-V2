from __future__ import annotations

from typing import Any

from backend.app.services.evidence_analysis import (
    aggregate_evidence,
    assess_provenance_quality,
    detect_source_conflicts,
)
from backend.app.services.nutrition.nutrient_validation import (
    nutrient_value_status,
)


def assess_food_quality(
    food: Any,
    evidence_documents: list[Any] | None = None,
) -> dict[str, Any]:
    """Assess catalog nutrition-data quality and supporting evidence.

    This does not assess physical freshness, spoilage, contamination,
    adulteration or overall food safety.
    """
    nutrients = list(food.nutrients or [])

    counts = {"available": 0, "missing": 0, "invalid": 0}
    invalid_reasons: dict[str, int] = {}
    nutrient_results = []
    evidence_items = []

    food_provenance = {
        "food_id": food.id,
        "source": food.source,
        "external_id": food.external_id,
        "source_url": food.source_url,
    }

    food_assessment = assess_provenance_quality({
        "source_type": "food",
        "provenance": food_provenance,
    })

    for nutrient in nutrients:
        status = nutrient_value_status(
            nutrient.amount,
            nutrient.basis_g,
        )

        if status == "valid":
            counts["available"] += 1
        elif status == "missing":
            counts["missing"] += 1
        else:
            counts["invalid"] += 1
            invalid_reasons[status] = invalid_reasons.get(status, 0) + 1

        provenance = {
            "food_id": food.id,
            "food_name": food.name,
            "nutrient_key": nutrient.nutrient_key,
            "amount": str(nutrient.amount) if nutrient.amount is not None else None,
            "unit": nutrient.unit,
            "basis_g": str(nutrient.basis_g) if nutrient.basis_g is not None else None,
            "source": nutrient.source,
            "source_nutrient_id": nutrient.source_nutrient_id,
            "derivation_code": nutrient.derivation_code,
            "derivation_description": nutrient.derivation_description,
            "derivation_source_description": nutrient.derivation_source_description,
        }

        provenance_assessment = assess_provenance_quality({
            "source_type": "nutrient",
            "provenance": provenance,
        })

        # The shared provenance validator checks numeric completeness but
        # does not reject negative numeric values. Apply nutrient validation.
        if status == "negative_amount":
            provenance_assessment["status"] = "invalid"
            provenance_assessment["issues"].append(
                "Nutrient measurement is negative."
            )

        evidence_items.append({
            "source_type": "nutrient",
            "source_id": f"{food.id}:{nutrient.nutrient_key}",
            "title": f"{nutrient.display_name} in {food.name}",
            "provenance": provenance,
            "provenance_records": [provenance],
        })

        nutrient_results.append({
            "nutrient_key": nutrient.nutrient_key,
            "display_name": nutrient.display_name,
            "amount": str(nutrient.amount) if nutrient.amount is not None else None,
            "unit": nutrient.unit,
            "basis_g": str(nutrient.basis_g) if nutrient.basis_g is not None else None,
            "status": status,
            "source": nutrient.source,
            "source_nutrient_id": nutrient.source_nutrient_id,
            "derivation_metadata_available": bool(nutrient.derivation_code),
            "provenance_assessment": provenance_assessment,
        })

    # Only use indexed nutrient evidence explicitly associated with this food.
    for document in evidence_documents or []:
        provenance = document.provenance or {}

        if (
            document.source_type == "nutrient"
            and document.status == "indexed"
            and str(provenance.get("food_id")) == str(food.id)
            and provenance.get("nutrient_key")
        ):
            evidence_items.append({
                "source_type": "nutrient",
                "source_id": str(document.source_id),
                "title": document.title,
                "content": document.content,
                "provenance": provenance,
                "provenance_records": [provenance],
            })

    aggregated = aggregate_evidence(evidence_items)
    conflicts = detect_source_conflicts(aggregated)

    total = sum(counts.values())
    coverage = round(counts["available"] * 100 / total, 2) if total else None

    if total == 0:
        assessment_status = "no_nutrient_data"
    elif counts["invalid"] or conflicts["conflicts"] or conflicts["invalid_evidence"]:
        assessment_status = "data_quality_issues"
    elif (
        counts["missing"]
        or conflicts["incomparable"]
        or food_assessment["status"] != "complete"
    ):
        assessment_status = "limited_data"
    else:
        assessment_status = "assessable"

    return {
        "food_id": food.id,
        "food_name": food.name,
        "assessment_status": assessment_status,
        "nutrient_summary": {
            "total_records": total,
            **counts,
            "coverage_percent": coverage,
            "invalid_reasons": invalid_reasons,
        },
        "food_provenance": food_assessment,
        "nutrients": nutrient_results,
        "source_conflicts": conflicts["conflicts"],
        "incomparable_measurements": conflicts["incomparable"],
        "invalid_evidence": conflicts["invalid_evidence"],
        "regulatory_context": {
            "status": "not_assessed",
            "reason": (
                "Regulatory records do not currently have a structured "
                "food identifier association."
            ),
        },
        "limitations": [
            "This assessment evaluates catalog nutritional data and evidence metadata only.",
            "It does not determine physical freshness, spoilage, adulteration, contamination or overall food safety.",
            "Missing information is not evidence of a food-quality defect.",
            "Source attribution does not independently establish source accuracy.",
        ],
    }
