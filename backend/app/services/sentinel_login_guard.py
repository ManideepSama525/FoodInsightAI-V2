"""Account-scoped test guard, only after Sentinel confirms a new detection.

Does not trust client-supplied IP headers, affect ordinary accounts, block an
IP, or disable the independent FoodInsightAI login throttle. Default OFF.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from backend.app.models.sentinel_login_hold import SentinelLoginHold
from backend.app.services.login_throttle import _account_hash

PROBE_DESCRIPTION = "Synthetic Sentinel login-protection probe: authentication failed"
PROBE_PATTERN = re.compile(r"^sentinel-probe-[0-9a-f]{24}@sentinel-test\.invalid$")
ACCOUNT_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
INCIDENT_PATTERN = re.compile(r"^INC-\d{6}$")
EVENT_PATTERN = re.compile(r"^[0-9a-f]{32}$")
HOLD_SECONDS = 60
_ACTION_NAMESPACE = UUID("968d80a9-2a68-4db1-8dc1-ce8392868903")


def enabled() -> bool:
    return os.getenv("SENTINEL_LOGIN_GUARD_ENABLED", "") == "1"


def is_probe_email(email: str) -> bool:
    return isinstance(email, str) and bool(
        PROBE_PATTERN.fullmatch(email.strip().casefold())
    )


def _now(value=None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def seconds_remaining(db: Session, email: str, now=None) -> int:
    """Return zero except for opted-in, precisely formatted synthetic identities."""
    if not enabled() or not is_probe_email(email):
        return 0
    record = db.get(SentinelLoginHold, _account_hash(email))
    if record is None:
        return 0
    remaining = (record.expires_at - _now(now)).total_seconds()
    return max(0, math.ceil(remaining))


def confirmed_new_detection(payload: dict, ack: dict) -> tuple[str, str, str] | None:
    """Accept only this queue event's exact Sentinel detection acknowledgement."""
    if not enabled() or not isinstance(payload, dict) or not isinstance(ack, dict):
        return None
    if (
        payload.get("source") != "FoodInsightAI"
        or payload.get("event_type") != "authentication"
        or payload.get("description") != PROBE_DESCRIPTION
        or payload.get("status_code") != 401
        or payload.get("method") != "POST"
        or str(payload.get("path", "")).rstrip("/")
           not in ("/auth/login", "/api/v1/auth/login")
        or payload.get("user_id") is not None
        or not ACCOUNT_HASH_PATTERN.fullmatch(str(payload.get("account_id_hash", "")))
        or not EVENT_PATTERN.fullmatch(str(payload.get("event_id", "")))
        or ack.get("accepted") is not True
        or ack.get("duplicate") is not False
        or ack.get("event_id") != payload.get("event_id")
        or not isinstance(ack.get("detections"), list)
    ):
        return None
    for detection in ack["detections"]:
        if not isinstance(detection, dict):
            continue
        incident_id = detection.get("incident_id")
        if (
            detection.get("attack") == "Brute Force"
            and detection.get("matched_rule") == "AUTH_BRUTE_FORCE_001"
            and detection.get("created") is True
            and isinstance(incident_id, str)
            and INCIDENT_PATTERN.fullmatch(incident_id)
        ):
            return (payload["account_id_hash"], incident_id, payload["event_id"])
    return None


def persist_confirmed_hold(
    db: Session, payload: dict, ack: dict, *, now=None
) -> bool:
    """Idempotently record a 60-second hold; never extend it on replay."""
    match = confirmed_new_detection(payload, ack)
    if match is None:
        return False
    account_hash, incident_id, trigger_event_id = match
    action_id = str(uuid5(_ACTION_NAMESPACE, incident_id + ":" + account_hash))
    existing = db.get(SentinelLoginHold, account_hash)
    if existing is not None and existing.action_id == action_id:
        return False
    now_value = _now(now)
    if existing is not None and existing.expires_at > now_value:
        # Do not allow overlapping incidents to lengthen an active hold.
        return False
    if existing is None:
        existing = SentinelLoginHold(account_hash=account_hash)
        db.add(existing)
    existing.action_id = action_id
    existing.incident_id = incident_id
    existing.trigger_event_id = trigger_event_id
    existing.created_at = now_value
    existing.expires_at = now_value + timedelta(seconds=HOLD_SECONDS)
    db.commit()
    return True
