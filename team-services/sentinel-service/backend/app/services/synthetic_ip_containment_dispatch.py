"""Guarded, test-only synthetic IP response dispatch.

This module is not connected to ingestion or running API routes.
The caller must explicitly opt in and inject a transport. No default
network transport exists. The caller must obtain policy evidence from
the persisted event database, not from untrusted request data.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.synthetic_ip_containment_action import (
    SyntheticIPContainmentAction,
)
from app.services.synthetic_ip_containment_policy import (
    evaluate_synthetic_ip_containment,
)


def _utc_naive(value):
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _result(record, duplicate=False, dispatched=False):
    expiry = record.confirmed_expires_at
    return {
        "action_id": record.action_id,
        "incident_id": record.incident_id,
        "source_ip": record.source_ip,
        "status": record.status,
        "attempt_count": record.attempt_count,
        "duplicate": duplicate,
        "dispatched": dispatched,
        "confirmed_expires_at": (
            expiry.isoformat() + "Z" if expiry else None
        ),
        "last_error": record.last_error,
    }


def dispatch_test_ip_containment(
    db,
    incident,
    evidence,
    *,
    action_id,
    reason,
    response_token,
    transport,
    test_mode_enabled=False,
    now=None,
):
    """Persist PENDING before transport, and SUCCESS only after confirmation.

    transport(payload, headers) is injected for offline tests.
    Real HTTP dispatch must be separately reviewed and explicitly wired.
    """
    if test_mode_enabled is not True:
        raise ValueError("Synthetic dispatch is disabled.")

    if not callable(transport):
        raise ValueError("An explicit test transport is required.")

    if not isinstance(response_token, str) or len(response_token) < 16:
        raise ValueError("Response channel credentials are unavailable.")

    try:
        canonical_id = str(UUID(str(action_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid action ID.") from exc

    if canonical_id != action_id:
        raise ValueError("Action ID must be canonical.")

    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 350:
        raise ValueError("A meaningful response reason is required.")

    reason = reason.strip()
    now = _utc_naive(now or datetime.now(timezone.utc))

    existing_by_id = db.scalar(
        select(SyntheticIPContainmentAction).where(
            SyntheticIPContainmentAction.action_id == canonical_id
        )
    )
    existing_by_incident = db.scalar(
        select(SyntheticIPContainmentAction).where(
            SyntheticIPContainmentAction.incident_id
            == incident.incident_id
        )
    )

    if existing_by_incident is not None and (
        existing_by_id is None
        or existing_by_incident.id != existing_by_id.id
    ):
        raise ValueError(
            "Incident already has another containment action."
        )

    if existing_by_id is not None:
        if (
            existing_by_id.incident_id != incident.incident_id
            or existing_by_id.source_ip != incident.source_ip
            or existing_by_id.reason != reason
            or existing_by_id.duration_seconds != 30
        ):
            raise ValueError("Action ID conflicts with stored response.")

        if existing_by_id.status == "SUCCESS":
            return _result(existing_by_id, duplicate=True)

        if existing_by_id.status == "PENDING":
            raise ValueError(
                "Action already pending; cannot dispatch concurrently."
            )

        if existing_by_id.status != "FAILED":
            raise ValueError("Unsupported stored response state.")

    decision = evaluate_synthetic_ip_containment(
        incident,
        evidence,
        existing_action=False,
        test_mode_enabled=True,
    )

    if decision["decision"] != "ELIGIBLE_TEST_CONTAINMENT":
        raise ValueError(
            "Containment policy rejected incident: "
            + decision["reason"]
        )

    if (
        decision["automation_authorized"] is not False
        or decision["action_executed"] is not False
        or decision["duration_seconds"] != 30
    ):
        raise ValueError("Unexpected policy authorization state.")

    if existing_by_id is None:
        record = SyntheticIPContainmentAction(
            action_id=canonical_id,
            incident_id=incident.incident_id,
            source_ip=incident.source_ip,
            duration_seconds=30,
            reason=reason,
            status="PENDING",
            attempt_count=1,
            last_error=None,
        )
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(
                "Concurrent containment action detected."
            ) from exc
    else:
        record = existing_by_id
        record.status = "PENDING"
        record.attempt_count += 1
        record.last_error = None
        record.updated_at = now
        db.commit()

    request_body = {
        "action_id": canonical_id,
        "incident_id": incident.incident_id,
        "source_ip": incident.source_ip,
        "duration_seconds": 30,
        "reason": reason,
    }
    headers = {
        "X-Sentinel-Response-Token": response_token,
    }

    try:
        response = transport(request_body, headers)
        if not isinstance(response, dict):
            raise RuntimeError("Invalid response type.")

        if response.get("status_code") not in (200, 201):
            raise RuntimeError("Target rejected containment request.")

        data = response.get("body")
        if not isinstance(data, dict):
            raise RuntimeError("Target returned invalid response body.")

        if not all((
            data.get("accepted") is True,
            data.get("result") == "SUCCESS",
            data.get("action_id") == canonical_id,
            data.get("incident_id") == incident.incident_id,
            data.get("source_ip") == incident.source_ip,
            data.get("active") is True,
            data.get("enforcement_scope") == "SYNTHETIC_TEST_IP_ONLY",
            data.get("firewall_modified") is False,
        )):
            raise RuntimeError("Target did not confirm matching containment.")

        raw_expiry = data.get("expires_at")
        if not isinstance(raw_expiry, str):
            raise RuntimeError("Target did not provide an expiry.")

        expiry = datetime.fromisoformat(
            raw_expiry.replace("Z", "+00:00")
        )
        if expiry.tzinfo is None:
            raise RuntimeError("Target expiry has no timezone.")

        expiry = _utc_naive(expiry)
        if not (
            now < expiry <= now + timedelta(seconds=40)
        ):
            raise RuntimeError("Target expiry is outside permitted window.")

    except Exception as exc:
        record.status = "FAILED"
        record.last_error = (
            "Target confirmation unavailable: " + type(exc).__name__
        )
        record.updated_at = now
        db.commit()
        return _result(record, dispatched=True)

    record.status = "SUCCESS"
    record.confirmed_expires_at = expiry
    record.last_error = None
    record.updated_at = now
    db.commit()

    return _result(record, dispatched=True)
