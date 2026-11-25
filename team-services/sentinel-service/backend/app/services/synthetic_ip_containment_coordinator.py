"""Database-verified coordination of test-only IP containment.

Not attached to ingestion or public API endpoints. Callers cannot supply
their own evidence dictionaries. No network transport is created here.
"""
from sqlalchemy import select

from app.models.incident import Incident
from app.models.response_action import ResponseAction
from app.models.synthetic_ip_containment_action import (
    SyntheticIPContainmentAction,
)
from app.services.response_policy import collect_bruteforce_evidence
from app.services.synthetic_ip_containment_policy import (
    evaluate_synthetic_ip_containment,
)
from app.services.synthetic_ip_containment_dispatch import (
    dispatch_test_ip_containment,
)


def coordinate_test_ip_containment(
    db,
    *,
    incident_id,
    action_id,
    reason,
    response_token,
    transport,
    enabled=False,
    now=None,
):
    """Coordinate a single verified test action with persistent evidence.

    Existing session-revocation actions are not modified or overridden.
    This operation is disabled unless enabled is explicitly True.
    """

    if enabled is not True:
        raise ValueError("IP containment coordination is disabled.")

    if not isinstance(incident_id, str):
        raise ValueError("Invalid incident ID.")

    if not callable(transport):
        raise ValueError("An explicit transport is required.")

    incident = db.scalar(
        select(Incident).where(
            Incident.incident_id == incident_id
        )
    )
    if incident is None:
        raise ValueError("Incident does not exist.")

    # Session revocation is governed by a separate analyst-approved
    # workflow. Do not silently add an IP action to such an incident.
    account_action = db.scalar(
        select(ResponseAction).where(
            ResponseAction.incident_id == incident_id
        )
    )
    if account_action is not None:
        raise ValueError(
            "Incident already has an account-specific response action."
        )

    previous = db.scalar(
        select(SyntheticIPContainmentAction).where(
            SyntheticIPContainmentAction.incident_id == incident_id
        )
    )

    if previous is not None and previous.action_id != action_id:
        raise ValueError(
            "Incident already has a different IP-containment action."
        )

    # Verified evidence is loaded from persisted security telemetry.
    # The caller cannot bypass this by presenting an evidence object.
    evidence = collect_bruteforce_evidence(db, incident)

    decision = evaluate_synthetic_ip_containment(
        incident,
        evidence,
        existing_action=False,
        test_mode_enabled=True,
    )

    if decision["decision"] != "ELIGIBLE_TEST_CONTAINMENT":
        raise ValueError(
            "Persisted evidence rejected containment: "
            + decision["reason"]
        )

    if not evidence.get("verified"):
        raise ValueError("Persisted evidence was not verified.")

    result = dispatch_test_ip_containment(
        db,
        incident,
        evidence,
        action_id=action_id,
        reason=reason,
        response_token=response_token,
        transport=transport,
        test_mode_enabled=True,
        now=now,
    )

    return {
        **result,
        "evidence_verified_from_database": True,
        "verified_failed_logins": evidence["evidence_count"],
        "trigger_event_id": evidence["trigger_event_id"],
        "target_confirmation_recorded": result["status"] == "SUCCESS",
        "middleware_enforcement_verified": False,
        "real_ip_containment_enabled": False,
    }
