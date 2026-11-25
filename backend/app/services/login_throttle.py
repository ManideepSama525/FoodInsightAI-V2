import hashlib
import hmac
import math
import os

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.models.login_throttle import LoginThrottleState


FAILURE_WINDOW_SECONDS = 900
THRESHOLD = 5
BASE_COOLDOWN_SECONDS = 15
MAX_COOLDOWN_SECONDS = 300


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _account_hash(email: str) -> str:
    key = os.getenv("SENTINEL_ACCOUNT_HASH_KEY", "")

    if not key:
        raise RuntimeError("Account hashing key is not configured.")

    normalized = email.strip().casefold()

    return hmac.new(
        key.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_login_cooldown_seconds(db: Session, email: str) -> int:
    digest = _account_hash(email)
    state = db.get(LoginThrottleState, digest)

    if state is None or state.blocked_until is None:
        return 0

    remaining = (state.blocked_until - _utcnow()).total_seconds()

    if remaining <= 0:
        return 0

    return max(1, math.ceil(remaining))


def register_failed_login(db: Session, email: str) -> int:
    digest = _account_hash(email)
    now = _utcnow()

    state = db.get(LoginThrottleState, digest)

    if state is None:
        state = LoginThrottleState(
            account_hash=digest,
            failure_count=1,
            window_started_at=now,
            blocked_until=None,
            updated_at=now,
        )
        db.add(state)

    elif (
        state.window_started_at is None
        or now - state.window_started_at
        >= timedelta(seconds=FAILURE_WINDOW_SECONDS)
    ):
        state.failure_count = 1
        state.window_started_at = now
        state.blocked_until = None
        state.updated_at = now

    else:
        state.failure_count += 1
        state.updated_at = now

    if state.failure_count >= THRESHOLD:
        exponent = min(state.failure_count - THRESHOLD, 5)

        cooldown = min(
            BASE_COOLDOWN_SECONDS * (2 ** exponent),
            MAX_COOLDOWN_SECONDS,
        )

        state.blocked_until = now + timedelta(seconds=cooldown)

    else:
        state.blocked_until = None

    db.commit()

    return state.failure_count


def clear_login_failures(db: Session, email: str) -> None:
    digest = _account_hash(email)
    state = db.get(LoginThrottleState, digest)

    if state is not None:
        db.delete(state)
        db.commit()
