"""Independent, dry-run containment policy for synthetic test sources.

Does not execute actions, change incidents, alter session-revocation
policy, or write to a database.
"""
import ipaddress
import math

from app.services.response_policy import (
    collect_bruteforce_evidence,
)

POLICY_VERSION = "SYNTHETIC_IP_1.0"
MIN_FAILED_LOGINS = 5
MIN_CONFIDENCE = 80.0
DURATION_SECONDS = 30

TEST_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
    )
)


def allowed_synthetic_ip(source_ip):
    if not isinstance(source_ip, str):
        return False
    try:
        address = ipaddress.ip_address(source_ip)
    except ValueError:
        return False
    return (
        isinstance(address, ipaddress.IPv4Address)
        and str(address) == source_ip
        and any(address in network for network in TEST_NETWORKS)
    )


def evaluate_synthetic_ip_containment(
    incident,
    evidence,
    *,
    existing_action=False,
    test_mode_enabled=False,
):
    """Return an eligibility decision only, never perform containment."""

    source_ip = getattr(incident, "source_ip", None)
    attack = str(getattr(incident, "attack_type", "") or "")
    severity = str(getattr(incident, "severity", "") or "")
    status = str(getattr(incident, "status", "") or "")

    try:
        confidence = float(getattr(incident, "confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0

    if not math.isfinite(confidence):
        confidence = 0.0

    # Incident confidence is stored on a 0..100 scale.
    confidence = max(0.0, min(100.0, confidence))

    try:
        evidence_count = int(evidence.get("evidence_count", 0))
    except (TypeError, ValueError, OverflowError):
        evidence_count = 0

    trigger = getattr(incident, "trigger_event_id", None)

    result = {
        "policy_version": POLICY_VERSION,
        "decision": "REJECT",
        "recommended_action": "NONE",
        "reason": "",
        "source_ip": source_ip,
        "incident_id": getattr(incident, "incident_id", None),
        "evidence_count": evidence_count,
        "confidence": confidence,
        "duration_seconds": None,
        "eligible_for_test_dispatch": False,
        "automation_authorized": False,
        "action_executed": False,
        "execution_mode": "DRY_RUN",
    }

    def reject(reason):
        result["reason"] = reason
        return result

    if not test_mode_enabled:
        return reject("Synthetic containment test mode is disabled.")

    if status.casefold() != "active":
        return reject("Incident is not active.")

    if attack.casefold() != "brute force":
        return reject("Only verified brute-force attacks are eligible.")

    if severity.casefold() not in ("high", "critical"):
        return reject("Incident severity is below the containment threshold.")

    if confidence < MIN_CONFIDENCE:
        return reject("Detection confidence is below 80 percent.")

    if not allowed_synthetic_ip(source_ip):
        return reject("Source is not an approved synthetic test IP.")

    if existing_action:
        return reject("An action already exists for this incident.")

    if not all((
        getattr(incident, "target_user_id", None),
        getattr(incident, "target_account_hash", None),
        trigger,
    )):
        return reject("Exact account attribution is missing.")

    if (
        evidence.get("verified") is not True
        or evidence_count < MIN_FAILED_LOGINS
        or evidence.get("trigger_event_id") != trigger
    ):
        return reject("Verified repeated-login evidence is insufficient.")

    result.update({
        "decision": "ELIGIBLE_TEST_CONTAINMENT",
        "recommended_action": "TEMPORARY_IP_BLOCK",
        "reason": (
            "Verified repeated brute-force authentication failures "
            "against one account from an approved synthetic test source."
        ),
        "duration_seconds": DURATION_SECONDS,
        "eligible_for_test_dispatch": True,
    })
    return result


def evaluate_with_database(
    db,
    incident,
    *,
    existing_action=False,
    test_mode_enabled=False,
):
    """Collect actual stored login evidence before evaluating the policy."""
    if not test_mode_enabled:
        return evaluate_synthetic_ip_containment(
            incident,
            {},
            existing_action=existing_action,
            test_mode_enabled=False,
        )

    evidence = collect_bruteforce_evidence(db, incident)
    return evaluate_synthetic_ip_containment(
        incident,
        evidence,
        existing_action=existing_action,
        test_mode_enabled=True,
    )
