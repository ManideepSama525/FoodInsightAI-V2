"""Read-only, fail-closed FSSAI amendment registry access."""

import json
from datetime import date
from pathlib import Path

from backend.app.services.regulatory_rule_engine import summarize_amendments


REGISTRY_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "regulatory"
    / "fssai"
    / "labelling_amendments_consolidated_v1.json"
)


class RegistryUnavailable(RuntimeError):
    pass


def load_amendment_registry():
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RegistryUnavailable("Registry unavailable or invalid") from exc

    if not isinstance(data, dict):
        raise RegistryUnavailable("Registry must be an object")

    records = data.get("amendments")
    if not isinstance(records, list) or len(records) != 6:
        raise RegistryUnavailable("Unexpected amendment record count")

    ids = [item.get("amendment_id") for item in records if isinstance(item, dict)]
    if len(ids) != 6 or len(set(ids)) != 6:
        raise RegistryUnavailable("Duplicate or invalid amendment identifiers")

    if data.get("legal_review_complete") is not False:
        raise RegistryUnavailable("Unexpected legal review state")
    if data.get("compliance_rules_enabled") is not False:
        raise RegistryUnavailable("Unexpected rule activation state")

    if any(item.get("compliance_rules_enabled") is not False for item in records):
        raise RegistryUnavailable("Unapproved rule activation in source registry")

    return data


def amendment_status_on(assessment_date: date):
    data = load_amendment_registry()
    items = summarize_amendments(data, assessment_date.isoformat())

    return {
        "authority": "FSSAI",
        "jurisdiction": "India",
        "regulation_family": "Labelling and Display",
        "assessment_date": assessment_date.isoformat(),
        "amendment_count": len(items),
        "legal_review_complete": False,
        "compliance_rules_enabled": False,
        "product_compliance_assessed": False,
        "compliance_verdict": None,
        "notice": (
            "Informational amendment timeline only. "
            "Effective-date status does not establish legal compliance. "
            "Subsequent directions and clause-level review remain pending."
        ),
        "amendments": items,
    }
