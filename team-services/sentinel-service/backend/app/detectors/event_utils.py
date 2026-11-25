from datetime import datetime, timezone
from urllib.parse import urlsplit


def parse_event_time(event):
    value = (
        event.get("timestamp")
        or event.get("occurred_at")
        or event.get("created_at")
    )

    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        result = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)

    return result.astimezone(timezone.utc)


def get_client_key(event):
    value = (
        event.get("client_id")
        or event.get("client_fingerprint")
        or event.get("source_ip")
        or event.get("ip")
    )

    if not value:
        return None

    return str(value).strip().lower() or None


def get_account_key(event):
    value = event.get("account_id_hash") or event.get("account_key")

    if not value:
        return None

    return str(value).strip() or None


def get_request_path(event):
    value = event.get("route_template") or event.get("path") or ""
    return urlsplit(str(value)).path.rstrip("/").lower() or "/"


def is_within_window(event, now, window_seconds):
    timestamp = parse_event_time(event)

    if timestamp is None:
        return False

    age = (now - timestamp).total_seconds()
    return 0 <= age <= window_seconds