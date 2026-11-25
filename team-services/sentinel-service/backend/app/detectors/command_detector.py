import re

from app.detectors.request_utils import extract_request_payload


COMMAND_PATTERNS = [
    (
        "SHELL_COMMAND_CHAIN",
        re.compile(
            r"(?:;|&&|\|\||\|)\s*"
            r"(?:whoami|id|uname|pwd|cat|type|dir|curl|wget|"
            r"powershell(?:\.exe)?|cmd(?:\.exe)?|bash|sh|"
            r"netcat|nc|python(?:3)?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "WINDOWS_COMMAND_EXECUTION",
        re.compile(
            r"\bcmd(?:\.exe)?\s+/(?:c|k)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "POWERSHELL_EXECUTION",
        re.compile(
            r"\bpowershell(?:\.exe)?\b.{0,100}"
            r"\s-(?:command|enc|encodedcommand)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "SHELL_INTERPRETER_EXECUTION",
        re.compile(
            r"\b/(?:bin|usr/bin)/(?:ba)?sh\s+-c\b",
            re.IGNORECASE,
        ),
    ),
    (
        "COMMAND_SUBSTITUTION",
        re.compile(
            r"\$\(\s*(?:whoami|id|uname|pwd|cat|curl|wget|"
            r"python|bash|sh)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "BACKTICK_COMMAND_SUBSTITUTION",
        re.compile(
            r"`\s*(?:whoami|id|uname|pwd|cat|curl|wget)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "STANDALONE_SHELL_COMMAND",
        re.compile(
            r"^\s*(?:whoami|uname|pwd)\s*$",
            re.IGNORECASE,
        ),
    ),
]


def detect_command_injection(request):
    payload = extract_request_payload(request)

    for rule_name, pattern in COMMAND_PATTERNS:
        if pattern.search(payload):
            return {
                "detected": True,
                "attack": "Command Injection",
                "severity": "High",
                "confidence": 89.0,
                "explanation": (
                    "Suspicious shell execution pattern detected: "
                    f"{rule_name}"
                ),
                "matched_rule": rule_name,
            }

    return {"detected": False}