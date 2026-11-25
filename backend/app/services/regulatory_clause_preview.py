"""Preliminary FSSAI provision-to-label evidence mapping.

Only existing registered amendments are considered.
These are provision candidates, NOT approved executable rules.
No compliance or violation decision may be produced.
"""

from backend.app.services.regulatory_registry import (
    load_amendment_registry,
)

# Discovery hints only. NOT legal obligations or predicates.
FIELD_HINTS = {
    "Regulation 5": ("nutrition_section",),
    "Regulation 6": ("allergens", "ingredients"),
    "Regulation 7": ("ingredients",),
    "Schedule-II paragraph 2.6": ("ingredients",),
    "Schedule-II paragraph 2.2": ("ingredients",),
}

def map_clause_evidence(
    screening_result: dict,
    label_fields: list,
) -> dict:
    registry = load_amendment_registry()

    if registry.get("compliance_rules_enabled") is not False:
        raise ValueError("Unapproved rule activation")

    if registry.get("legal_review_complete") is not False:
        raise ValueError("Unexpected legal approval state")

    amendments = {
        item["amendment_id"]: item
        for item in registry["amendments"]
    }

    observed = {
        item.get("field"): item
        for item in label_fields
        if isinstance(item, dict)
        and item.get("verification_status")
            == "EXTRACTED_UNVERIFIED"
    }

    candidates = []
    for candidate in screening_result.get(
        "candidate_amendments", []
    ):
        identifier = candidate.get("amendment_id")
        source = amendments.get(identifier)

        if source is None:
            raise ValueError("Unknown amendment reference")

        if source.get("compliance_rules_enabled") is not False:
            raise ValueError("Amendment is unexpectedly enabled")

        if (
            candidate.get("product_applicability_verified")
            is not False
        ):
            raise ValueError("Unsupported applicability approval")

        for provision in source.get("affected_provisions", []):
            hints = FIELD_HINTS.get(provision, ())
            evidence = []

            for field in hints:
                record = observed.get(field)
                if record:
                    evidence.append({
                        "field": field,
                        "value": record.get("value"),
                        "evidence_text": record.get("evidence_text"),
                        "line_number": record.get("line_number"),
                        "verification_status": "EXTRACTED_UNVERIFIED",
                    })

            candidates.append({
                "amendment_id": identifier,
                "provision_reference": provision,
                "date_status": candidate.get("date_status"),
                "source_text_sha256": source.get(
                    "extracted_text_sha256"
                ),
                "suggested_evidence_fields": list(hints),
                "extracted_evidence": evidence,
                "field_mapping_status": (
                    "PRELIMINARY_HINT"
                    if hints else "NOT_YET_MAPPED"
                ),
                "product_applicability_verified": False,
                "legal_review_status": "PENDING",
                "requirement_text_verified": False,
                "exceptions_checked": False,
                "supersession_checked": False,
                "rule_executed": False,
                "compliance_verdict": None,
                "finding_status": "NEEDS_LEGAL_REVIEW",
            })

    return {
        "provision_candidate_count": len(candidates),
        "provision_candidates": candidates,
        "legal_review_complete": False,
        "rule_execution_performed": False,
        "compliance_verdict": None,
        "notice": (
            "Provision references are discovery candidates. "
            "Field mappings are preliminary hints, not verified "
            "statutory requirements. Extracted label evidence "
            "is unverified. No legal compliance determination "
            "has been performed."
        ),
    }
