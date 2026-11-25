from datetime import datetime, timezone

from app.detectors.event_utils import (
    get_client_key,
    get_account_key,
    is_within_window,
)


LOGIN_PATHS = {
    "/api/v1/auth/login",
    "/auth/login",
    "/login",
}


def _is_authentication_event(event):
    event_type = str(event.get("event_type", "")).lower()
    path = str(event.get("path", "")).lower().rstrip("/")
    method = str(event.get("method", "")).upper()

    return (
        event_type in {
            "authentication",
            "authentication_attempt",
            "login",
            "login_attempt",
        }
        or (method == "POST" and path in LOGIN_PATHS)
    )


def _is_failed_login(event):
    outcome = str(event.get("outcome", "")).lower()

    return (
        event.get("success") is False
        or outcome in {
            "failure",
            "failed",
            "invalid_credentials",
            "denied",
        }
        or (
            event.get("status_code") == 401
            and _is_authentication_event(event)
        )
    )


def detect_bruteforce(
    event,
    history,
    threshold=5,
    window_seconds=300,
    now=None,
):
    if threshold < 2 or window_seconds <= 0:
        raise ValueError("Invalid brute-force threshold.")

    if not _is_authentication_event(event):
        return {"detected": False}

    if not _is_failed_login(event):
        return {"detected": False}

    client = get_client_key(event)

    if not client:
        return {"detected": False}

    now = now or datetime.now(timezone.utc)
    account = get_account_key(event)

    matching = []

    for item in list(history) + [event]:
        if not _is_authentication_event(item):
            continue

        if not _is_failed_login(item):
            continue

        if get_client_key(item) != client:
            continue

        if account and get_account_key(item) != account:
            continue

        if is_within_window(item, now, window_seconds):
            matching.append(item)

    count = len(matching)

    if count < threshold:
        return {"detected": False}

    return {
        "detected": True,
        "attack": "Brute Force",
        "severity": "High",
        "confidence": 85.0,
        "rule_confidence": 85.0,
        "matched_rule": "AUTH_BRUTE_FORCE_001",
        "explanation": (
            f"{count} failed authentication attempts "
            f"from one client within {window_seconds} seconds."
        ),
        "attempt_count": count,
        "window_seconds": window_seconds,
        "action": "MONITOR",
    }


def detect_credential_stuffing(
    event,
    history,
    threshold=10,
    window_seconds=300,
    now=None,
):
    if threshold < 2 or window_seconds <= 0:
        raise ValueError("Invalid credential-stuffing threshold.")

    if not _is_authentication_event(event):
        return {"detected": False}

    if not _is_failed_login(event):
        return {"detected": False}

    client = get_client_key(event)

    if not client:
        return {"detected": False}

    now = now or datetime.now(timezone.utc)
    accounts = set()

    for item in list(history) + [event]:
        if not _is_authentication_event(item):
            continue

        if not _is_failed_login(item):
            continue

        if get_client_key(item) != client:
            continue

        if not is_within_window(item, now, window_seconds):
            continue

        account = get_account_key(item)

        if account:
            accounts.add(account)

    if len(accounts) < threshold:
        return {"detected": False}

    return {
        "detected": True,
        "attack": "Credential Stuffing",
        "severity": "High",
        "confidence": 85.0,
        "rule_confidence": 85.0,
        "matched_rule": "AUTH_CREDENTIAL_STUFFING_001",
        "explanation": (
            f"Authentication failures against {len(accounts)} "
            f"distinct accounts within {window_seconds} seconds."
        ),
        "distinct_accounts": len(accounts),
        "window_seconds": window_seconds,
        "action": "MONITOR",
    }