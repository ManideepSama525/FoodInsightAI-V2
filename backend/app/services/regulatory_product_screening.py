"""Conservative product-to-amendment screening.

Category mappings are discovery hints, not legal applicability findings.
No product compliance conclusions are generated.
"""

from datetime import date

from backend.app.services.regulatory_registry import (
    load_amendment_registry,
)
from backend.app.services.regulatory_rule_engine import (
    summarize_amendments,
)

CATEGORY_HINTS = {
    "bread": {"FSSAI-LABEL-AMEND-2", "FSSAI-LABEL-AMEND-3"},
    "coffee_chicory": {"FSSAI-LABEL-AMEND-2", "FSSAI-LABEL-AMEND-4"},
    "milk_product": {"FSSAI-LABEL-AMEND-2", "FSSAI-LABEL-AMEND-6"},
    "edible_oil": {"FSSAI-LABEL-AMEND-1", "FSSAI-LABEL-AMEND-2"},
    "sweetener_product": {
        "FSSAI-LABEL-AMEND-1",
        "FSSAI-LABEL-AMEND-2",
        "FSSAI-LABEL-AMEND-5",
    },
    "other": set(),
}

def screen_product(product_type: str, assessment_date: date):
    registry = load_amendment_registry()
    if product_type not in CATEGORY_HINTS:
        raise ValueError("Unsupported product category")

    timeline = summarize_amendments(
        registry, assessment_date.isoformat()
    )
    by_id = {item["amendment_id"]: item for item in timeline}
    records = {
        item["amendment_id"]: item
        for item in registry["amendments"]
    }

    candidates = []
    for identifier in sorted(CATEGORY_HINTS[product_type]):
        amendment = records[identifier]
        timeline_item = by_id[identifier]
        candidates.append({
            "amendment_id": identifier,
            "date_status": timeline_item["status"],
            "affected_provisions": amendment["affected_provisions"],
            "source_text_sha256": amendment["extracted_text_sha256"],
            "screening_status": "PENDING_LEGAL_REVIEW",
            "product_applicability_verified": False,
            "compliance_verdict": None,
        })

    return {
        "product_type": product_type,
        "assessment_date": assessment_date.isoformat(),
        "jurisdiction": "India",
        "authority": "FSSAI",
        "screening_only": True,
        "assessment_complete": False,
        "product_compliance_assessed": False,
        "compliance_verdict": None,
        "candidate_amendments": candidates,
        "candidate_count": len(candidates),
        "notice": (
            "Category-based discovery only. This is not a complete "
            "list of applicable laws. Product facts, other regulations, "
            "exemptions, legal amendments and directions require review. "
            "No legal compliance finding has been made."
        ),
    }
