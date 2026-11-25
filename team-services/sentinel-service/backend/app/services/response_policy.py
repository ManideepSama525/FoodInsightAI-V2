import math
from datetime import datetime, timedelta, timezone

from app.models.security_event import SecurityEvent


POLICY_VERSION = "2D.1"

AUTH_PATHS = (
    "/auth/login",
    "/api/v1/auth/login",
)

MINIMUM_FAILED_LOGINS = 5
EVIDENCE_WINDOW_SECONDS = 300
TRIGGER_TIME_TOLERANCE_SECONDS = 30
MINIMUM_CONFIDENCE = 80.0


def _utc_naive(value):
    if value is None:
        return None

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


def normalized_confidence(value):
    try:
        confidence = float(value or 0)
    except (TypeError, ValueError):
        return 0.0

    if not math.isfinite(confidence):
        return 0.0

    if 0.0 <= confidence <= 1.0:
        confidence *= 100.0

    return min(100.0, max(0.0, confidence))


def collect_bruteforce_evidence(db, incident):
    """Verify exact account attribution and failed authentication evidence."""

    result = {
        "verified": False,
        "evidence_count": 0,
        "trigger_event_id": getattr(incident, "trigger_event_id", None),
        "reason": "Account-specific evidence was not verified.",
    }

    if getattr(incident, "attack_type", "") != "Brute Force":
        result["reason"] = "This response policy requires a brute-force incident."
        return result

    user_id = getattr(incident, "target_user_id", None)
    account_hash = getattr(incident, "target_account_hash", None)
    trigger_id = getattr(incident, "trigger_event_id", None)
    source_ip = getattr(incident, "source_ip", None)

    if not all((user_id, account_hash, trigger_id, source_ip)):
        result["reason"] = "Account attribution is incomplete."
        return result

    trigger = db.query(SecurityEvent).filter(
        SecurityEvent.event_id == trigger_id,
        SecurityEvent.source == "FoodInsightAI",
        SecurityEvent.event_type == "authentication",
        SecurityEvent.user_id == user_id,
        SecurityEvent.account_id_hash == account_hash,
        SecurityEvent.source_ip == source_ip,
        SecurityEvent.status_code == 401,
        SecurityEvent.method == "POST",
        SecurityEvent.path.in_(AUTH_PATHS),
    ).first()

    if trigger is None:
        result["reason"] = "The exact linked authentication event could not be verified."
        return result

    incident_time = _utc_naive(getattr(incident, "created_at", None))
    event_time = _utc_naive(trigger.received_at)

    if incident_time is None or event_time is None:
        result["reason"] = "Incident or event timestamp is unavailable."
        return result

    tolerance = timedelta(seconds=TRIGGER_TIME_TOLERANCE_SECONDS)

    if not (
        incident_time - tolerance
        <= event_time
        <= incident_time + tolerance
    ):
        result["reason"] = "The linked event falls outside the incident time boundary."
        return result

    count = db.query(SecurityEvent).filter(
        SecurityEvent.source == "FoodInsightAI",
        SecurityEvent.event_type == "authentication",
        SecurityEvent.user_id == user_id,
        SecurityEvent.account_id_hash == account_hash,
        SecurityEvent.source_ip == source_ip,
        SecurityEvent.status_code == 401,
        SecurityEvent.method == "POST",
        SecurityEvent.path.in_(AUTH_PATHS),
        SecurityEvent.received_at >= (
            event_time - timedelta(seconds=EVIDENCE_WINDOW_SECONDS)
        ),
        SecurityEvent.received_at <= event_time,
    ).count()

    result["evidence_count"] = count

    if count < MINIMUM_FAILED_LOGINS:
        result["reason"] = (
            "Fewer than five verified failed logins exist in the evidence window."
        )
        return result

    result["verified"] = True
    result["reason"] = (
        "Exact account attribution, trigger event, and failed-login evidence verified."
    )

    return result


def evaluate_response_policy(
    incident,
    evidence,
    response_action_exists=False,
):
    """Return a dry-run decision. This function never executes an action."""

    severity = str(getattr(incident, "severity", "") or "").strip().casefold()
    attack_type = str(getattr(incident, "attack_type", "") or "").strip().casefold()
    status = str(getattr(incident, "status", "") or "").strip().casefold()

    confidence = normalized_confidence(
        getattr(incident, "confidence", None)
    )

    evidence_count = int(evidence.get("evidence_count", 0) or 0)
    evidence_verified = bool(evidence.get("verified", False))

    def result(decision, action, reason, approval=False):
        return {
            "policy_version": POLICY_VERSION,
            "decision": decision,
            "recommended_action": action,
            "reason": reason,
            "severity": getattr(incident, "severity", None),
            "confidence_score": confidence,
            "evidence_count": evidence_count,
            "evidence_verified": evidence_verified,
            "requires_approval": approval,
            "automation_authorized": False,
            "execution_mode": "DRY_RUN",
            "trigger_event_id": evidence.get("trigger_event_id"),
        }

    if status != "active":
        return result(
            "REJECT_RESPONSE",
            "NONE",
            "Incident is not active.",
        )

    if response_action_exists:
        return result(
            "REJECT_RESPONSE",
            "NONE",
            "A response action already exists for this incident. Use its original action ID for any permitted retry.",
        )

    if severity == "low":
        return result(
            "MONITOR",
            "MONITOR",
            "Low-severity activity. No containment action is recommended.",
        )

    if severity == "medium":
        return result(
            "INVESTIGATE",
            "MANUAL_INVESTIGATION",
            "Medium-severity activity requires analyst review.",
        )

    if severity not in ("high", "critical"):
        return result(
            "INVESTIGATE",
            "MANUAL_INVESTIGATION",
            "Unknown severity requires manual classification.",
        )

    if attack_type != "brute force":
        return result(
            "INVESTIGATE",
            "MANUAL_INVESTIGATION",
            "High-impact containment is not authorized by this policy for this attack type.",
        )

    if not all((
        getattr(incident, "target_user_id", None),
        getattr(incident, "target_account_hash", None),
        getattr(incident, "trigger_event_id", None),
    )):
        return result(
            "REJECT_RESPONSE",
            "MANUAL_INVESTIGATION",
            "Account-specific response rejected because incident attribution is incomplete.",
        )

    if not evidence_verified:
        return result(
            "REJECT_RESPONSE",
            "MANUAL_INVESTIGATION",
            evidence.get("reason", "Required account evidence is missing."),
        )

    if confidence < MINIMUM_CONFIDENCE:
        return result(
            "INVESTIGATE",
            "MANUAL_INVESTIGATION",
            "Verified account evidence exists, but confidence is below the policy threshold.",
        )

    return result(
        "REQUIRES_ANALYST_APPROVAL",
        "REVOKE_USER_SESSIONS",
        "High-confidence account-attributed brute force with verified failed-login evidence. Explicit analyst approval is required.",
        approval=True,
    )
