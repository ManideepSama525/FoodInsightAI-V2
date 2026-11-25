"""Conservative, deterministic FSSAI regulatory rule assessment.

This module does not certify legal compliance. Rules must be separately
verified and approved before any satisfaction/violation verdict.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import re


def _date(value):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _trusted_source(rule):
    url = rule.get("source_url", "")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    sha = rule.get("source_sha256", "")
    return (
        parsed.scheme == "https"
        and (host == "fssai.gov.in" or host.endswith(".fssai.gov.in"))
        and isinstance(sha, str)
        and bool(re.fullmatch(r"[0-9a-fA-F]{64}", sha))
    )


def assess_rule(rule, facts, assessment_date, jurisdiction="India"):
    """Evaluate a structured rule; fail closed when evidence is incomplete."""
    rule_id = rule.get("rule_id", "unknown")
    result = {
        "rule_id": rule_id,
        "status": "NEEDS_REVIEW",
        "reason": "",
        "assessment_date": str(assessment_date),
        "source_url": rule.get("source_url"),
        "legal_certification": False,
    }

    def finish(status, reason):
        result["status"] = status
        result["reason"] = reason
        return result

    when = _date(assessment_date)
    effective = _date(rule.get("effective_date"))

    if when is None or effective is None:
        return finish("NEEDS_REVIEW", "Assessment or effective date unverified")

    if jurisdiction != "India" or rule.get("jurisdiction") != "India":
        return finish("NOT_APPLICABLE", "Rule is scoped to India")

    if when < effective:
        return finish("NOT_YET_EFFECTIVE", "Rule is not in force on assessment date")

    expiry_raw = rule.get("end_date")
    if expiry_raw:
        expiry = _date(expiry_raw)
        if expiry is None:
            return finish("NEEDS_REVIEW", "Invalid end date")
        if when >= expiry:
            return finish("NEEDS_REVIEW", "Rule version expired; replacement must be checked")

    if (
        rule.get("enabled") is not True
        or rule.get("legal_review_status") != "verified"
        or rule.get("supersession_review") != "verified"
        or not _trusted_source(rule)
    ):
        return finish("NEEDS_REVIEW", "Legal source, review or activation is incomplete")

    applicability = rule.get("applicability", {})
    if not isinstance(applicability, dict):
        return finish("NEEDS_REVIEW", "Invalid applicability metadata")

    for key, expected in applicability.items():
        if key not in facts or facts[key] is None:
            return finish("INSUFFICIENT_DATA", "Missing applicability fact: " + key)
        if facts[key] != expected:
            return finish("NOT_APPLICABLE", "Product is outside rule scope")

    predicate = rule.get("predicate", {})
    if not isinstance(predicate, dict):
        return finish("NEEDS_REVIEW", "Invalid predicate")

    field = predicate.get("field")
    operator = predicate.get("operator")
    if not isinstance(field, str) or not field:
        return finish("NEEDS_REVIEW", "Missing predicate field")

    if field not in facts or facts[field] is None:
        return finish("INSUFFICIENT_DATA", "Missing required fact: " + field)

    actual = facts[field]
    target = predicate.get("value")

    if operator == "equals":
        if target is None:
            return finish("NEEDS_REVIEW", "Missing expected value")
        passed = type(actual) is type(target) and actual == target
    elif operator in ("minimum", "maximum"):
        if isinstance(actual, bool) or isinstance(target, bool):
            return finish("NEEDS_REVIEW", "Numeric predicate requires numbers")
        if predicate.get("unit") is None or facts.get(field + "_unit") != predicate["unit"]:
            return finish("INSUFFICIENT_DATA", "Missing or incompatible measurement unit")
        try:
            actual_number = Decimal(str(actual))
            target_number = Decimal(str(target))
            if not actual_number.is_finite() or not target_number.is_finite():
                raise InvalidOperation()
        except (InvalidOperation, ValueError, TypeError):
            return finish("INSUFFICIENT_DATA", "Invalid numeric measurement")
        passed = (
            actual_number >= target_number
            if operator == "minimum"
            else actual_number <= target_number
        )
    else:
        return finish("NEEDS_REVIEW", "Unsupported predicate operator")

    if passed:
        return finish("COMPLIANT", "Supplied facts satisfy this verified rule only")
    return finish("NON_COMPLIANT", "Supplied facts violate this verified rule only")


def summarize_amendments(registry, assessment_date):
    """Date-aware visibility, not a legal-compliance determination."""
    when = _date(assessment_date)
    if when is None:
        raise ValueError("Invalid assessment date")

    results = []
    for item in registry.get("amendments", []):
        effective = _date(item.get("effective_date"))
        if effective is None:
            status = "EFFECTIVE_DATE_UNRESOLVED"
        elif when < effective:
            status = "FUTURE_REQUIREMENT"
        else:
            status = "PENDING_LEGAL_REVIEW"

        results.append({
            "amendment_id": item["amendment_id"],
            "effective_date": item.get("effective_date"),
            "status": status,
            "compliance_verdict": None,
        })

    return results
