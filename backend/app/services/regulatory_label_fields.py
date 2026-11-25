"""Conservative deterministic extraction of food-label declarations.

Fields are text candidates, never verified regulatory facts.
No LLM, external requests, persistence, or compliance conclusions.
"""

import re

MAX_INPUT = 15000
MAX_FIELD_VALUE = 1200
FIELD_NAMES = (
    "ingredients",
    "allergens",
    "nutrition_section",
    "fssai_licence_number",
    "net_quantity",
    "manufacture_date",
    "best_before",
    "expiry_date",
)

HEADING_RE = re.compile(
    r"^(?:ingredients?|ingredient list|allergens?|allergy advice|"
    r"contains|nutrition(?:al)? (?:information|facts)|"
    r"fssai|net (?:wt|weight|quantity|qty)|net contents?|"
    r"mfg|manufactur(?:ing|ed)|packed on|best before|"
    r"expiry|exp(?:iry)? date)\b",
    re.IGNORECASE,
)

PATTERNS = (
    (
        "ingredients",
        re.compile(
            r"^(?:ingredients?|ingredient list)\s*[:\-]\s*(.+)$",
            re.IGNORECASE,
        ),
    ),
    (
        "allergens",
        re.compile(
            r"^(?:allergens?|allergy advice|contains)\s*[:\-]\s*(.+)$",
            re.IGNORECASE,
        ),
    ),
    (
        "nutrition_section",
        re.compile(
            r"^(?:nutrition(?:al)? (?:information|facts)|"
            r"nutrition facts)\s*[:\-]?\s*(.*)$",
            re.IGNORECASE,
        ),
    ),
    (
        "net_quantity",
        re.compile(
            r"^(?:net (?:wt|weight|quantity|qty)\.?|net contents?)"
            r"\s*[:\-]?\s*(\d+(?:\.\d+)?\s*"
            r"(?:kg|g|ml|l|litre|liter|grams))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "manufacture_date",
        re.compile(
            r"^(?:mfg(?:\.?\s*date)?|manufactur(?:ing|ed)"
            r"(?:\s*date)?|packed on)\s*[:\-]\s*(.{3,60})$",
            re.IGNORECASE,
        ),
    ),
    (
        "best_before",
        re.compile(
            r"^best before\s*[:\-]\s*(.{3,60})$",
            re.IGNORECASE,
        ),
    ),
    (
        "expiry_date",
        re.compile(
            r"^(?:expiry(?:\s*date)?|exp\.?\s*date)"
            r"\s*[:\-]\s*(.{3,60})$",
            re.IGNORECASE,
        ),
    ),
)

LICENCE_PATTERN = re.compile(
    r"\b(?:FSSAI(?:\s+(?:LIC(?:EN[CS]E)?|REGISTRATION))?"
    r"|LICEN[CS]E\s+NO\.?)\s*(?:NO\.?)?\s*[:#.-]?\s*"
    r"([0-9][0-9\s-]{12,22}[0-9])",
    re.IGNORECASE,
)


def extract_label_fields(text: str) -> dict:
    if not isinstance(text, str):
        raise TypeError("Document text must be a string")

    source = text[:MAX_INPUT]
    lines = [
        (number, " ".join(raw.split()))
        for number, raw in enumerate(source.splitlines(), 1)
        if raw.strip()
    ]

    results = []
    present = set()

    def add(field, value, line, line_number):
        value = " ".join(value.split()).strip(" :-")
        if not value or field in present:
            return
        present.add(field)
        results.append({
            "field": field,
            "value": value[:MAX_FIELD_VALUE],
            "evidence_text": line[:MAX_FIELD_VALUE],
            "line_number": line_number,
            "verification_status": "EXTRACTED_UNVERIFIED",
        })

    for index, (line_number, line) in enumerate(lines):
        licence = LICENCE_PATTERN.search(line)
        if licence and "fssai_licence_number" not in present:
            digits = re.sub(r"\D", "", licence.group(1))
            if len(digits) == 14:
                add(
                    "fssai_licence_number", digits,
                    line, line_number,
                )

        for field, pattern in PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            value = match.group(1).strip()

            if field == "nutrition_section":
                continuation = []
                for _, following in lines[index + 1:index + 9]:
                    if HEADING_RE.match(following):
                        break
                    continuation.append(following)
                value = " ".join([value, *continuation]).strip()
                if not value:
                    continue

            if field == "ingredients" and not value:
                continue

            if field in ("manufacture_date", "best_before", "expiry_date"):
                value = value[:60]

            add(field, value, line, line_number)

    return {
        "extraction_method": "DETERMINISTIC_TEXT_PATTERNS",
        "source_text_truncated": len(text) > MAX_INPUT,
        "fields": results,
        "detected_field_count": len(results),
        "not_detected": [
            name for name in FIELD_NAMES if name not in present
        ],
        "facts_verified": False,
        "compliance_verdict": None,
        "notice": (
            "Text-pattern matches are unverified candidates. "
            "OCR errors, nonstandard layouts and missing declarations "
            "can cause missed or incorrect matches. "
            "Not detected does not mean legally missing."
        ),
    }
