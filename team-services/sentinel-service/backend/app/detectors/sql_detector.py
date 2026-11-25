import re
from urllib.parse import unquote_plus


SQL_RULES = [
    (
        "UNION_SELECT",
        re.compile(r"\bunion\s+(?:all\s+)?select\b", re.IGNORECASE),
    ),
    (
        "NUMERIC_BOOLEAN_TAUTOLOGY",
        re.compile(r"\b(?:or|and)\s+\d+\s*=\s*\d+\b", re.IGNORECASE),
    ),
    (
        "QUOTED_BOOLEAN_COMPARISON",
        re.compile(
            r"""\b(?:or|and)\s+(?P<q>['"])(?P<left>[^'"]{1,32})(?P=q)\s*=\s*(?P=q)(?P<right>[^'"]{1,32})(?:(?P=q)|(?=$|\s|--|#))""",
            re.IGNORECASE,
        ),
    ),
    (
        "SQL_COMMENT_TERMINATOR",
        re.compile(r"""['"]\s*(?:--|#)"""),
    ),
    (
        "DDL_COMMAND",
        re.compile(
            r"\b(?:drop|alter|truncate)\s+(?:table|database|schema)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "DATABASE_METADATA",
        re.compile(r"\binformation_schema\b", re.IGNORECASE),
    ),
    (
        "TIME_DELAY",
        re.compile(r"\b(?:sleep|benchmark)\s*\(", re.IGNORECASE),
    ),
    (
        "SQL_SERVER_COMMAND",
        re.compile(r"\b(?:waitfor\s+delay|xp_cmdshell)\b", re.IGNORECASE),
    ),
    (
        "DATABASE_FILE_ACCESS",
        re.compile(
            r"\bload_file\s*\(|\binto\s+(?:outfile|dumpfile)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "STACKED_SQL_STATEMENT",
        re.compile(
            r";\s*(?:select|insert|update|delete|drop|alter|truncate)\b",
            re.IGNORECASE,
        ),
    ),
]


def _request_payload(request):
    parts = []

    for key in ("query", "body", "path"):
        value = request.get(key, "")

        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")

        if value is not None:
            parts.append(str(value))

    payload = " ".join(parts)

    for _ in range(3):
        decoded = unquote_plus(payload)

        if decoded == payload:
            break

        payload = decoded

    return payload.lower()


def detect_sql_injection(request):
    payload = _request_payload(request)

    for rule_name, pattern in SQL_RULES:
        if pattern.search(payload):
            return {
                "detected": True,
                "attack": "SQL Injection",
                "severity": "High",
                "confidence": 89.0,
                "explanation": (
                    "SQL injection signature detected: "
                    f"{rule_name}"
                ),
                "matched_rule": rule_name,
            }

    return {"detected": False}