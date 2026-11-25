"""Safe Sentinel enforcement adapter.

Global source-IP blocking is intentionally disabled. FoodInsightAI clients can
share a Docker bridge address, so an IP is not a safe account identity. The
SOC may still block an individual suspicious request with HTTP 403, while
account-specific responses must use the authenticated user/session workflow.
"""


def block_ip(ip: str) -> None:
    """Compatibility no-op: never add a source IP to a global block list."""
    return None


def unblock_ip(ip: str) -> None:
    """Compatibility no-op: global source-IP enforcement is disabled."""
    return None


def is_ip_blocked(ip: str) -> bool:
    """Global IP blocking is disabled for safety."""
    return False


def get_blocked_ips() -> list[str]:
    """Return an empty list because no IPs are globally blocked."""
    return []
