from datetime import datetime, timezone

from app.detectors.event_utils import (
    get_client_key,
    get_request_path,
    is_within_window,
)


RESOURCE_PREFIXES = (
    "/recognition",
    "/freshness",
    "/food-fraud",
    "/rag",
    "/nutrition/foods/usda",
    "/uploads",
)


def _is_request_event(event):
    event_type = str(event.get("event_type", "")).lower()

    return (
        event_type in {
            "request",
            "http_request",
            "api_request",
        }
        or (
            bool(event.get("method"))
            and bool(event.get("path"))
        )
    )


def _is_resource_intensive(path):
    # Support both standalone service paths and FoodInsightAI API paths.
    prefixes = RESOURCE_PREFIXES + tuple(
        "/api/v1" + prefix for prefix in RESOURCE_PREFIXES
    )

    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in prefixes
    )


def detect_api_abuse(
    event,
    history,
    max_requests=120,
    window_seconds=60,
    expensive_max_requests=20,
    unauthorized_threshold=10,
    min_unique_paths=5,
    now=None,
):
    if min(
        max_requests,
        expensive_max_requests,
        unauthorized_threshold,
        min_unique_paths,
    ) < 1:
        raise ValueError("Detection thresholds must be positive.")

    if window_seconds <= 0:
        raise ValueError("Window must be positive.")

    if not _is_request_event(event):
        return {"detected": False}

    client = get_client_key(event)

    if not client:
        return {"detected": False}

    now = now or datetime.now(timezone.utc)

    recent = [
        item
        for item in list(history) + [event]
        if (
            _is_request_event(item)
            and get_client_key(item) == client
            and is_within_window(item, now, window_seconds)
        )
    ]

    if len(recent) >= max_requests:
        return {
            "detected": True,
            "attack": "API Request Flooding",
            "severity": "High",
            "confidence": 85.0,
            "rule_confidence": 85.0,
            "matched_rule": "API_REQUEST_FLOOD_001",
            "request_count": len(recent),
            "window_seconds": window_seconds,
            "action": "MONITOR",
        }

    resource_events = [
        item for item in recent
        if _is_resource_intensive(get_request_path(item))
    ]

    if len(resource_events) >= expensive_max_requests:
        return {
            "detected": True,
            "attack": "Resource Intensive API Abuse",
            "severity": "High",
            "confidence": 85.0,
            "rule_confidence": 85.0,
            "matched_rule": "API_RESOURCE_ABUSE_001",
            "request_count": len(resource_events),
            "window_seconds": window_seconds,
            "action": "MONITOR",
        }

    unauthorized = [
        item for item in recent
        if item.get("status_code") in (401, 403)
    ]

    unique_paths = {
        get_request_path(item) for item in unauthorized
    }

    if (
        len(unauthorized) >= unauthorized_threshold
        and len(unique_paths) >= min_unique_paths
    ):
        return {
            "detected": True,
            "attack": "Unauthorized API Probing",
            "severity": "Medium",
            "confidence": 85.0,
            "rule_confidence": 85.0,
            "matched_rule": "API_UNAUTHORIZED_PROBE_001",
            "request_count": len(unauthorized),
            "distinct_paths": len(unique_paths),
            "window_seconds": window_seconds,
            "action": "MONITOR",
        }

    return {"detected": False}