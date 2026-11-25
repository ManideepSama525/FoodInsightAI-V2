import re

from app.detectors.request_utils import extract_request_payload


XSS_RULES = [
    (
        "SCRIPT_TAG",
        re.compile(r"<\s*script\b", re.IGNORECASE),
    ),
    (
        "HTML_EVENT_HANDLER",
        re.compile(
            r"<[^>]{0,500}\bon[a-z]{3,24}\s*=",
            re.IGNORECASE,
        ),
    ),
    (
        "JAVASCRIPT_URI",
        re.compile(
            r"""(?:href|src|action|formaction)\s*=\s*["']?\s*javascript\s*:""",
            re.IGNORECASE,
        ),
    ),
    (
        "DATA_HTML_URI",
        re.compile(
            r"""(?:src|href)\s*=\s*["']?\s*data\s*:\s*text/html""",
            re.IGNORECASE,
        ),
    ),
]


def detect_xss(request):
    payload = extract_request_payload(request)

    for rule_name, pattern in XSS_RULES:
        if pattern.search(payload):
            return {
                "detected": True,
                "attack": "Cross Site Scripting",
                "severity": "High",
                "confidence": 89.0,
                "explanation": (
                    "Suspicious HTML/script pattern detected: "
                    f"{rule_name}"
                ),
                "matched_rule": rule_name,
            }

    return {"detected": False}