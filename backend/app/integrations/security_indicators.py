from __future__ import annotations

import json
import re
from urllib.parse import unquote_plus
from typing import Any

MAX_INSPECT_BODY_BYTES = 64 * 1024
MAX_INSPECT_QUERY_CHARS = 4096

# Conservative, high-specificity signatures. These inspect content locally and
# return only fixed rule identifiers; matched text is never returned.
_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "FOOD_SQLI_001",
        "SQL Injection",
        (
            r"\bunion\s+(?:all\s+)?select\b",
            r"\b(?:or|and)\s+1\s*=\s*1\b",
            r"['\"]\s*(?:or|and)\s+['\"]?1['\"]?\s*=\s*['\"]?1",
            r"\b(?:sleep|benchmark)\s*\(",
            r"\b(?:information_schema|xp_cmdshell)\b",
            r"\b(?:drop|alter|truncate)\s+(?:table|database)\b",
        ),
    ),
    (
        "FOOD_XSS_001",
        "Cross Site Scripting",
        (
            r"<\s*script\b",
            r"javascript\s*:",
            r"data\s*:\s*text/html\b",
            r"\bon[a-z]{3,}\s*=\s*['\"]?\s*(?:javascript\s*:|alert\s*\(|prompt\s*\(|confirm\s*\()",
            r"<\s*(?:iframe|svg)\b[^>]*\bonload\s*=",
            r"document\s*\.\s*cookie",
        ),
    ),
    (
        "FOOD_CMDI_001",
        "Command Injection",
        (
            r"(?:;|&&|\|\|)\s*(?:whoami|id|uname|cat|curl|wget|powershell|cmd(?:\.exe)?|bash|sh)\b",
            r"\bpowershell(?:\.exe)?\s+-(?:enc|encodedcommand|command)\b",
            r"\bcmd(?:\.exe)?\s+/c\s+(?:whoami|dir|type|ipconfig|powershell)\b",
            r"(?:`|\$\()\s*(?:whoami|id|uname|cat|curl|wget|powershell|bash|sh)\b",
        ),
    ),
    (
        "FOOD_PATH_001",
        "Directory Traversal",
        (
            r"(?:\.\./|\.\.\\)",
            r"/etc/passwd\b",
            r"/proc/self/environ\b",
            r"\bwindows[\\/]system32\b",
            r"\bboot\.ini\b",
        ),
    ),
)

_COMPILED = tuple(
    (rule_id, attack, tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns))
    for rule_id, attack, patterns in _RULES
)


def should_capture_request_body(path: str, content_type: str, content_length: str | None) -> bool:
    normalized_path = (path or "").casefold().rstrip("/")
    if normalized_path.endswith("/auth/login") or normalized_path.endswith("/auth/register"):
        return False

    media_type = (content_type or "").split(";", 1)[0].strip().casefold()
    if media_type not in {"application/json", "application/x-www-form-urlencoded"}:
        return False

    try:
        length = int(content_length or "-1")
    except (TypeError, ValueError):
        return False

    return 0 < length <= MAX_INSPECT_BODY_BYTES


def detect_payload_indicators(
    *,
    path: str,
    query: str = "",
    body: bytes = b"",
) -> list[dict[str, str]]:
    """Return fixed attack labels/rule IDs only; never return source content."""
    normalized_path = (path or "").casefold().rstrip("/")
    if normalized_path.endswith("/auth/login") or normalized_path.endswith("/auth/register"):
        return []

    safe_path = (path or "")[:2048]
    safe_query = (query or "")[:MAX_INSPECT_QUERY_CHARS]
    try:
        body_text = (body or b"")[:MAX_INSPECT_BODY_BYTES].decode("utf-8", errors="ignore")
    except (AttributeError, UnicodeError):
        body_text = ""

    # Decode JSON string escapes before scanning. Some clients serialize HTML
    # delimiters as \\u003c / \\u003e; raw regex scanning alone would miss those.
    decoded_body_values = [body_text]
    try:
        parsed_body = json.loads(body_text)
    except (json.JSONDecodeError, TypeError):
        parsed_body = None

    def collect_json_strings(value: Any) -> None:
        if isinstance(value, str):
            decoded_body_values.append(value)
        elif isinstance(value, dict):
            for nested_value in value.values():
                collect_json_strings(nested_value)
        elif isinstance(value, list):
            for nested_value in value:
                collect_json_strings(nested_value)

    if parsed_body is not None:
        collect_json_strings(parsed_body)

    candidate = unquote_plus(
        " ".join([safe_path, safe_query, *decoded_body_values])
    ).casefold()
    if not candidate.strip():
        return []

    matches: list[dict[str, str]] = []
    for rule_id, attack, patterns in _COMPILED:
        if any(pattern.search(candidate) for pattern in patterns):
            matches.append({"rule_id": rule_id, "attack": attack})

    return matches