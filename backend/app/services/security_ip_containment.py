"""Fail-closed temporary IP containment for isolated test networks.

This stage is deliberately not connected to live request middleware.
No system firewall operations are performed.
"""
import ipaddress
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.security_ip_block import SecurityIPBlock


_TEST_NETWORKS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
)

MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 300


def _utc_naive(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def validate_test_source_ip(raw):
    if not isinstance(raw, str):
        raise ValueError("A source IP string is required.")

    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise ValueError("Invalid source IP.") from exc

    if not isinstance(address, ipaddress.IPv4Address):
        raise ValueError("Only approved IPv4 test sources are supported.")

    if str(address) != raw:
        raise ValueError("Source IP must be canonical.")

    if not any(address in network for network in _TEST_NETWORKS):
        raise ValueError(
            "Source is not in the isolated test-IP allowlist."
        )

    return str(address)


def create_temporary_ip_block(
    db: Session,
    *,
    action_id: str,
    incident_id: str,
    source_ip: str,
    duration_seconds: int,
    reason: str,
    now=None,
):
    """Persist or idempotently replay the same test action."""
    try:
        canonical_action_id = str(UUID(str(action_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid action UUID.") from exc

    if canonical_action_id != str(action_id):
        raise ValueError("Action UUID must be canonical.")

    if not isinstance(incident_id, str) or not re.fullmatch(
        r"INC-\d{6}", incident_id
    ):
        raise ValueError("Invalid incident ID.")

    source_ip = validate_test_source_ip(source_ip)

    if (
        type(duration_seconds) is not int
        or not MIN_DURATION_SECONDS
        <= duration_seconds <= MAX_DURATION_SECONDS
    ):
        raise ValueError("Block duration outside permitted bounds.")

    if (
        not isinstance(reason, str)
        or not 10 <= len(reason.strip()) <= 500
    ):
        raise ValueError("A meaningful audit reason is required.")

    reason = reason.strip()
    now = _utc_naive(now)

    existing = db.scalar(
        select(SecurityIPBlock).where(
            SecurityIPBlock.action_id == canonical_action_id
        )
    )

    def replay(record):
        if (
            record.incident_id != incident_id
            or record.source_ip != source_ip
            or record.reason != reason
            or int(
                (record.expires_at - record.created_at)
                .total_seconds()
            ) != duration_seconds
        ):
            raise ValueError(
                "Action ID already belongs to a different containment."
            )
        return {
            "accepted": True,
            "duplicate": True,
            "action_id": record.action_id,
            "incident_id": record.incident_id,
            "source_ip": record.source_ip,
            "expires_at": record.expires_at.isoformat() + "Z",
            "active": now < record.expires_at,
            "result": record.result,
        }

    if existing is not None:
        return replay(existing)

    record = SecurityIPBlock(
        action_id=canonical_action_id,
        incident_id=incident_id,
        source_ip=source_ip,
        reason=reason,
        created_at=now,
        expires_at=now + timedelta(seconds=duration_seconds),
        performed_by="Sentinel-XDR",
        result="SUCCESS",
    )
    db.add(record)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(SecurityIPBlock).where(
                SecurityIPBlock.action_id == canonical_action_id
            )
        )
        if existing is None:
            raise
        return replay(existing)

    return {
        "accepted": True,
        "duplicate": False,
        "action_id": record.action_id,
        "incident_id": record.incident_id,
        "source_ip": record.source_ip,
        "expires_at": record.expires_at.isoformat() + "Z",
        "active": True,
        "result": record.result,
    }


def is_test_ip_blocked(db: Session, source_ip: str, now=None):
    """Expired rows are retained for audit but cease enforcement."""
    try:
        source_ip = validate_test_source_ip(source_ip)
    except ValueError:
        return False

    now = _utc_naive(now)

    record = db.scalar(
        select(SecurityIPBlock)
        .where(
            SecurityIPBlock.source_ip == source_ip,
            SecurityIPBlock.expires_at > now,
            SecurityIPBlock.result == "SUCCESS",
        )
        .order_by(SecurityIPBlock.expires_at.desc())
        .limit(1)
    )
    return record is not None
