from datetime import datetime, timedelta, timezone


def _utc_naive(value):
    if value is None:
        return None

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


def validate_approval_request(
    policy_record,
    incident,
    evidence,
    current_decision,
    now=None,
    max_age_seconds=600,
):
    """Validate a persisted dry-run decision and freshly rechecked evidence."""

    now = _utc_naive(now or datetime.utcnow())

    def reject(reason):
        return {"eligible": False, "reason": reason}

    if policy_record is None:
        return reject("Policy evaluation does not exist.")

    if incident is None:
        return reject("Incident does not exist.")

    if policy_record.incident_id != incident.incident_id:
        return reject("Policy evaluation does not belong to this incident.")

    if policy_record.decision != "REQUIRES_ANALYST_APPROVAL":
        return reject("Policy evaluation does not require analyst approval.")

    if policy_record.recommended_action != "REVOKE_USER_SESSIONS":
        return reject("Policy evaluation does not authorize this response type.")

    if policy_record.execution_mode != "DRY_RUN":
        return reject("The source evaluation was not recorded as a dry run.")

    if bool(policy_record.automation_authorized):
        return reject("Automated authorization is not permitted.")

    if not bool(policy_record.requires_approval):
        return reject("The source evaluation does not require explicit approval.")

    if not bool(policy_record.evidence_verified):
        return reject("The original policy evaluation did not verify its evidence.")

    if incident.status != "Active":
        return reject("Incident is not active.")

    if incident.attack_type != "Brute Force":
        return reject("Only account-attributed brute-force incidents are eligible.")

    if not all((
        incident.target_user_id,
        incident.target_account_hash,
        incident.trigger_event_id,
        incident.source_ip,
    )):
        return reject("Incident account attribution is incomplete.")

    if not bool(evidence.get("verified")):
        return reject(
            evidence.get("reason", "Fresh account-specific evidence was not verified.")
        )

    if int(evidence.get("evidence_count", 0) or 0) < 5:
        return reject("Fresh evidence contains fewer than five failed logins.")

    if evidence.get("trigger_event_id") != incident.trigger_event_id:
        return reject("Fresh evidence does not match the incident trigger event.")

    if policy_record.trigger_event_id != incident.trigger_event_id:
        return reject("Stored policy evaluation references a different trigger event.")

    if current_decision.get("decision") != "REQUIRES_ANALYST_APPROVAL":
        return reject("Fresh policy evaluation no longer permits approval.")

    if current_decision.get("recommended_action") != "REVOKE_USER_SESSIONS":
        return reject("Fresh policy evaluation recommends a different response.")

    if not current_decision.get("requires_approval"):
        return reject("Fresh policy evaluation does not require approval.")

    if current_decision.get("automation_authorized") is not False:
        return reject("Fresh policy evaluation has an invalid automation setting.")

    if not current_decision.get("evidence_verified"):
        return reject("Fresh policy evaluation evidence is not verified.")

    try:
        confidence = float(current_decision.get("confidence_score", 0))
    except (TypeError, ValueError):
        confidence = 0

    if confidence < 80:
        return reject("Fresh policy confidence is below the 80-point threshold.")

    if str(getattr(incident, "severity", "")).casefold() not in (
        "high",
        "critical",
    ):
        return reject("Incident severity is below the approval threshold.")

    if max_age_seconds is not None:
        created_at = _utc_naive(policy_record.created_at)

        if created_at is None:
            return reject("Policy evaluation timestamp is unavailable.")

        age = (now - created_at).total_seconds()

        if age < -30:
            return reject("Policy evaluation timestamp is in the future.")

        if age > max_age_seconds:
            return reject("Policy evaluation is older than the approval window.")

    return {
        "eligible": True,
        "reason": "Persisted policy, fresh evidence, and approval requirements verified.",
    }
