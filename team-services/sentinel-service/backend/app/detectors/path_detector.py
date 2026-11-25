import re

from app.detectors.request_utils import extract_request_payload


PATH_RULES = [
    (
        "RELATIVE_PATH_TRAVERSAL",
        re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|$)", re.IGNORECASE),
    ),
    (
        "WINDOWS_SYSTEM_PATH",
        re.compile(r"\bwindows[/\\]system32\b", re.IGNORECASE),
    ),
    (
        "LINUX_PASSWORD_FILE",
        re.compile(
            r"(?:^|[/\\])etc[/\\]passwd(?:$|[\s?#])",
            re.IGNORECASE,
        ),
    ),
    (
        "WINDOWS_BOOT_CONFIGURATION",
        re.compile(r"\bboot\.ini\b", re.IGNORECASE),
    ),
]


def detect_path_traversal(request):
    payload = extract_request_payload(request)

    for rule_name, pattern in PATH_RULES:
        if pattern.search(payload):
            return {
                "detected": True,
                "attack": "Directory Traversal",
                "severity": "High",
                "confidence": 89.0,
                "explanation": (
                    "Suspicious filesystem path detected: "
                    f"{rule_name}"
                ),
                "matched_rule": rule_name,
            }

    return {"detected": False}