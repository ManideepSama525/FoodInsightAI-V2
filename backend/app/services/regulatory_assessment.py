from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


FRESHNESS_LIMIT_DAYS = 180
CURRENT_DOCUMENT_STATUSES = {"active"}


def assess_regulatory_evidence(
    provenance: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    provenance = provenance or {}
    status = str(provenance.get("document_status") or "unknown").strip().lower()
    checked_value = provenance.get("last_checked_at")
    current_time = now or datetime.now(timezone.utc)

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    age_days = None
    parse_error = False

    if checked_value:
        try:
            checked_at = datetime.fromisoformat(
                str(checked_value).replace("Z", "+00:00")
            )
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            age_days = max(0, (current_time - checked_at).days)
        except (TypeError, ValueError):
            parse_error = True

    revalidation_due = (
        age_days is None
        or age_days > FRESHNESS_LIMIT_DAYS
        or parse_error
    )

    if status == "active" and not revalidation_due:
        assessment_status = "current_check"
        message = "Document is marked active and was checked within the freshness window."
    elif status == "active":
        assessment_status = "revalidation_due"
        message = "Document is marked active, but its last check is missing, invalid or older than 180 days."
    else:
        assessment_status = "not_current"
        message = f"Document status is '{status}'; it is excluded from current regulatory retrieval."

    return {
        "document_status": status,
        "last_checked_at": checked_value,
        "age_days": age_days,
        "freshness_limit_days": FRESHNESS_LIMIT_DAYS,
        "revalidation_due": revalidation_due,
        "eligible_for_current_retrieval": (status in CURRENT_DOCUMENT_STATUSES and not revalidation_due),
        "assessment_status": assessment_status,
        "message": message,
    }


def is_current_regulatory_evidence(provenance: dict[str, Any] | None) -> bool:
    assessment = assess_regulatory_evidence(provenance)
    return (
        (provenance or {}).get("record_type") == "regulatory_evidence"
        and (provenance or {}).get("official_domain_validated") is True
        and assessment["eligible_for_current_retrieval"]
    )
