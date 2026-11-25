"""Evidence-grounded preliminary product-label screening.

This module DOES NOT determine legal compliance.
OCR-derived fields are never automatically verified.
"""

import re
from datetime import date

from backend.app.services.regulatory_product_screening import (
    screen_product,
)

REVIEW_FIELDS = (
    "ingredients",
    "allergens",
    "nutrition_section",
    "fssai_licence_number",
    "net_quantity",
    "manufacture_date",
    "best_before",
    "expiry_date",
)

GAZETTE_MARKERS = (
    "gazette of india",
    "ministry of health and family welfare",
    "food safety and standards authority of india",
    "extraordinary part ii",
)


def assess_label_evidence(
    document: dict,
    product_type: str,
    assessment_date: date,
) -> dict:
    label_data = document.get("label_fields") or {}
    extracted_fields = label_data.get("fields") or []
    source_text = document.get("extracted_text") or ""

    field_map = {
        item["field"]: item
        for item in extracted_fields
        if item.get("field") in REVIEW_FIELDS
    }

    normalized = " ".join(source_text.lower().split())
    gazette_markers_found = [
        marker for marker in GAZETTE_MARKERS
        if marker in normalized
    ]

    appears_regulatory_source = (
        bool(gazette_markers_found)
        and len(field_map) < 2
    )

    document_kind = (
        "POSSIBLE_REGULATORY_NOTIFICATION"
        if appears_regulatory_source
        else "POSSIBLE_PRODUCT_LABEL"
        if len(field_map) >= 2
        else "DOCUMENT_TYPE_UNCERTAIN"
    )

    findings = []

    for field in REVIEW_FIELDS:
        evidence = field_map.get(field)

        if evidence is None:
            findings.append({
                "field": field,
                "status": "NOT_DETECTED",
                "severity": "INFORMATION_GAP",
                "value": None,
                "evidence_text": None,
                "line_number": None,
                "message": (
                    "This declaration was not detected in the "
                    "extracted text. This is not evidence of a "
                    "legal violation or that the declaration "
                    "is absent from the original packaging."
                ),
            })
            continue

        status = "EXTRACTED_UNVERIFIED"
        message = (
            "Text candidate found. Confirm against the "
            "original product label."
        )

        if field == "fssai_licence_number":
            number = re.sub(r"\D", "", str(evidence["value"]))
            if len(number) != 14:
                status = "REQUIRES_MANUAL_VERIFICATION"
                message = (
                    "The extracted number does not have "
                    "the expected 14-digit format."
                )
            elif len(set(number)) == 1:
                status = "SUSPECTED_TEST_OR_PLACEHOLDER_VALUE"
                message = (
                    "The number appears to be a synthetic "
                    "placeholder. It has not been checked "
                    "against official licensing records."
                )

        findings.append({
            "field": field,
            "status": status,
            "severity": "REVIEW_REQUIRED",
            "value": evidence.get("value"),
            "evidence_text": evidence.get("evidence_text"),
            "line_number": evidence.get("line_number"),
            "message": message,
        })

    # Existing category screening supplies candidate amendments,
    # not proven product applicability.
    regulatory = screen_product(product_type, assessment_date)

    # PHASE_3L2_CLAUSE_MAPPING
    from backend.app.services.regulatory_clause_preview import (
        map_clause_evidence,
    )
    try:
        clause_preview = map_clause_evidence(
            regulatory, extracted_fields
        )
    except ValueError as exc:
        # Clause mapping is supplementary. Never promote an
        # unknown amendment into a trusted legal rule.
        # Preserve the existing evidence assessment and make
        # the mapping failure explicit.
        clause_preview = {
            "status": "UNAVAILABLE_NEEDS_REVIEW",
            "provision_candidate_count": 0,
            "provision_candidates": [],
            "legal_review_complete": False,
            "rule_execution_performed": False,
            "compliance_verdict": None,
            "notice": (
                "Clause mapping unavailable: "
                + str(exc)
                + ". No compliance decision was made."
            ),
        }

    return {
        "product_type": product_type,
        "assessment_date": assessment_date.isoformat(),
        "document_type": document_kind,
        "document_type_verified": False,
        "document_sha256": document.get("sha256"),
        "text_extraction_status": document.get(
            "extraction_status", "UNKNOWN"
        ),
        "document_stored": False,
        "document_facts_verified": False,
        "assessment_complete": False,
        "legal_review_status": "PENDING",
        "compliance_verdict": None,
        "detected_field_count": len(field_map),
        "findings": findings,
        "clause_preview": clause_preview,
        "potentially_relevant_amendments": regulatory.get(
            "candidate_amendments", []
        ),
        "candidate_amendment_count": regulatory.get(
            "candidate_count", 0
        ),
        "source_document_warning": (
            "This appears to be a regulatory publication, "
            "not a product packaging label."
            if appears_regulatory_source else None
        ),
        "notice": (
            "Preliminary evidence review only. These are "
            "extraction findings, not confirmed FSSAI "
            "violations or compliance determinations. "
            "Applicable clauses, exemptions, effective dates "
            "and later directions require legal review."
        ),
    }
