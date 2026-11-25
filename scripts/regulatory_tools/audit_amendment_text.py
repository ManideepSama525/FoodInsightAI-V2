import re
import sys
from pathlib import Path

root = Path("data/regulatory/fssai/amendments")
output = Path("logs/regulatory_phase2i_amendment_content_audit.txt")

documents = [
    ("FSSAI-LABEL-AMEND-5", "labelling_amendment_2026_03_24.txt"),
    ("FSSAI-LABEL-AMEND-6", "labelling_amendment_2026_11_06.txt"),
]

patterns = [
    r"regulation\s+\d+",
    r"schedule\s*[-–]?\s*[IVX]+",
    r"shall\s+come\s+into\s+force",
    r"with\s+effect\s+from",
    r"exempt",
    r"substitut",
    r"insert",
    r"omit",
    r"2028",
]

lines = ["FOODINSIGHTAI PHASE 2I - AMENDMENT TEXT AUDIT"]
errors = []

for doc_id, filename in documents:
    path = root / filename
    lines.append("\n" + "=" * 75)
    lines.append("DOCUMENT: " + doc_id)
    lines.append("PATH: " + str(path))

    if not path.is_file():
        errors.append("Missing: " + str(path))
        lines.append("STATUS: MISSING")
        continue

    text = path.read_text(encoding="utf-8-sig")
    pages = re.findall(r"===== PAGE (\d+) =====", text)

    lines.append("STATUS: TEXT_PRESENT")
    lines.append("PAGES: " + str(len(pages)))
    lines.append("CHARACTERS: " + str(len(text)))
    lines.append("")
    lines.append("FIRST 4500 CHARACTERS:")
    lines.append(text[:4500])
    lines.append("")
    lines.append("REGULATORY KEYWORD CONTEXT:")

    seen = set()
    matches = 0

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 200)
            end = min(len(text), match.end() + 350)
            snippet = " ".join(text[start:end].split())
            key = (match.start() // 150, pattern)
            if key in seen:
                continue
            seen.add(key)
            lines.append("PATTERN: " + pattern)
            lines.append("CONTEXT: " + snippet)
            lines.append("---")
            matches += 1
            if matches >= 35:
                break
        if matches >= 35:
            break

    lines.append("MATCHES_REPORTED: " + str(matches))

lines.append("\nLEGAL EFFECTS VERIFIED: NO")
lines.append("AMENDMENTS APPLIED TO RULES: NO")
lines.append("DATABASE MODIFIED: NO")
lines.extend(errors)

output.write_text("\n".join(lines), encoding="utf-8")

print("DOCUMENTS:", len(documents))
print("ERRORS:", len(errors))
print("REPORT:", output)

if errors:
    sys.exit(1)
