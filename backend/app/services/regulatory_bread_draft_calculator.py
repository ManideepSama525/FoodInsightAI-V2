"""Non-executable legal draft: numerical bread formulation screening.

No FSSAI compliance decision is issued. Supplied formulation
percentages remain unverified and no transitional rule is applied.
"""
from decimal import Decimal, InvalidOperation

def compare_draft_bread(registry, bread_type, ingredient_percent):
    if (
        registry.get("compliance_rules_enabled") is not False
        or registry.get("legal_review_complete") is not False
        or registry.get("rule_execution_performed") is not False
    ):
        raise ValueError("Draft registry approval state invalid")

    requirements = registry.get("requirements")
    if not isinstance(requirements, list) or len(requirements) != 11:
        raise ValueError("Draft requirement registry invalid")

    matches = [
        item for item in requirements
        if item.get("product_category") == bread_type
    ]
    if len(matches) != 1:
        raise ValueError("Unsupported or ambiguous bread category")

    requirement = matches[0]
    if (
        requirement.get("rule_enabled") is not False
        or requirement.get("compliance_verdict") is not None
        or requirement.get("status") != "DRAFT_PENDING_LEGAL_REVIEW"
        or requirement.get("measurement_basis") != "100g_flour"
    ):
        raise ValueError("Draft requirement validation failed")

    result = {
        "bread_type": bread_type,
        "specialty_ingredient": requirement["specialty_ingredient"],
        "draft_minimum_percent": requirement[
            "candidate_minimum_percent"
        ],
        "measurement_basis": "100g_flour",
        "source_amendment_id": requirement["source_amendment_id"],
        "source_clause_id": requirement["source_clause_id"],
        "source_pdf_page": requirement["source_pdf_page"],
        "source_pdf_sha256": requirement["source_pdf_sha256"],
        "supplied_percent": None,
        "numerical_screening_status": "INSUFFICIENT_DATA",
        "product_facts_verified": False,
        "legal_review_complete": False,
        "rule_executed": False,
        "compliance_verdict": None,
        "notice": (
            "Draft arithmetic only using unverified formulation facts "
            "and a historically extracted amendment. This is not "
            "an FSSAI compliance or violation determination."
        ),
    }

    if bread_type == "multigrain_bread":
        result["numerical_screening_status"] = (
            "TRANSITIONAL_PERIOD_REVIEW_REQUIRED"
        )
        result["notice"] += (
            " Multigrain first-year transitional provisions "
            "must be independently reviewed."
        )
        return result

    if ingredient_percent is None or isinstance(
        ingredient_percent, bool
    ):
        return result

    try:
        actual = Decimal(str(ingredient_percent))
        minimum = Decimal(
            str(requirement["candidate_minimum_percent"])
        )
    except (InvalidOperation, ValueError, TypeError):
        return result

    if (
        not actual.is_finite()
        or not minimum.is_finite()
        or actual < 0
        or actual > 100
        or minimum < 0
        or minimum > 100
    ):
        return result

    result["supplied_percent"] = str(actual)
    result["numerical_screening_status"] = (
        "AT_OR_ABOVE_DRAFT_THRESHOLD"
        if actual >= minimum
        else "BELOW_DRAFT_THRESHOLD"
    )
    return result
