"""Draft bread ingredient screening.

Thresholds transcribed from the 2022 FSSAI labelling amendment.
Legal applicability, exceptions and later directions are not verified.
"""

from datetime import date
from backend.app.services.regulatory_registry import load_amendment_registry

DRAFT_THRESHOLDS = {
    "whole_wheat_bread": 75.0,
    "wheat_bread": 50.0,
    "brown_bread": 50.0,
}

def screen_bread_facts(
    bread_type: str,
    whole_wheat_flour_percent,
    assessment_date: date,
):
    registry = load_amendment_registry()
    source = next(
        (
            item for item in registry["amendments"]
            if item["amendment_id"] == "FSSAI-LABEL-AMEND-3"
        ),
        None,
    )
    if source is None:
        raise ValueError("Required amendment evidence missing")

    if bread_type not in DRAFT_THRESHOLDS:
        raise ValueError("Unsupported bread type")

    minimum = DRAFT_THRESHOLDS[bread_type]
    missing = []
    if whole_wheat_flour_percent is None:
        missing.append("whole_wheat_flour_percent_of_total_flour")

    return {
        "product_type": "bread",
        "bread_type": bread_type,
        "assessment_date": assessment_date.isoformat(),
        "jurisdiction": "India",
        "authority": "FSSAI",
        "rule_reference": "Schedule-II paragraph 2.6",
        "amendment_id": "FSSAI-LABEL-AMEND-3",
        "documented_effective_date": source["effective_date"],
        "source_text_sha256": source["extracted_text_sha256"],
        "minimum_whole_wheat_flour_percent_of_total_flour": minimum,
        "supplied_whole_wheat_flour_percent_of_total_flour": (
            whole_wheat_flour_percent
        ),
        "missing_facts": missing,
        "data_sufficiency": (
            "INSUFFICIENT_DATA" if missing else "FACTS_PROVIDED"
        ),
        "legal_review_status": "NEEDS_LEGAL_REVIEW",
        "threshold_assessment_performed": False,
        "product_compliance_assessed": False,
        "compliance_verdict": None,
        "notice": (
            "Draft ingredient screening only. The percentage is a "
            "source-derived candidate threshold, not an approved "
            "compliance rule. Exemptions, supersession, official "
            "directions and product formulation need verification."
        ),
    }
