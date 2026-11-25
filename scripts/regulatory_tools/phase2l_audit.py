import sys
import json
import re
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path("scripts/regulatory_tools/vendor").resolve()))
from pypdf import PdfReader

root = Path("data/regulatory/fssai/amendments/incoming")
report = Path("logs/regulatory_phase2l_report.txt")

files = {
    "FSSAI-LABEL-AMEND-1": "Gazette_Notification_Oil_Sweetner_16_09_2021.pdf",
    "FSSAI-LABEL-AMEND-2": "Gazette_Notification_FSS_Label_12_09_2022.pdf",
    "FSSAI-LABEL-AMEND-3": "Gazette_Notification_Labelling_14_10_2022.pdf",
    "FSSAI-LABEL-AMEND-4": "coffee chicory_gazette.pdf",
}

lines = ["FOODINSIGHTAI PHASE 2L - EARLIER AMENDMENT AUDIT"]
failed = 0

for doc_id, filename in files.items():
    path = root / filename
    lines.append("\n" + "=" * 70)
    lines.append("DOCUMENT: " + doc_id)
    lines.append("FILE: " + filename)

    try:
        data = path.read_bytes()
        if len(data) < 1000 or not data.startswith(b"%PDF-"):
            raise ValueError("PDF signature or size invalid")

        reader = PdfReader(str(path))
        pages = []
        low_text = []

        for index, page in enumerate(reader.pages, 1):
            content = page.extract_text() or ""
            pages.append("===== PAGE {} =====\n{}".format(index, content))
            if len(content.strip()) < 40:
                low_text.append(index)

        text = "\n\n".join(pages)
        output = root / (path.stem + ".txt")
        if output.exists():
            if output.read_text(encoding="utf-8") != text:
                raise RuntimeError("Existing extracted text differs; refusing overwrite")
        else:
            output.write_text(text, encoding="utf-8")

        lines.append("STATUS: EXTRACTED")
        lines.append("PDF_BYTES: " + str(len(data)))
        lines.append("PDF_SHA256: " + hashlib.sha256(data).hexdigest())
        lines.append("PAGE_COUNT: " + str(len(reader.pages)))
        lines.append("TEXT_CHARACTERS: " + str(len(text)))
        lines.append("LOW_TEXT_PAGES: " + str(low_text))
        lines.append("EXTRACTED_FILE: " + str(output))
        lines.append("")
        lines.append("LAST 5500 CHARACTERS:")
        lines.append(text[-5500:])
        lines.append("")
        lines.append("COMMENCEMENT AND PROVISION CONTEXT:")

        patterns = [
            r"shall come into force",
            r"shall be effective",
            r"with effect from",
            r"regulation\s+\d+",
            r"schedule\s*[-–]?\s*[IVX]+",
            r"coffee.{0,35}chicory",
        ]

        found = 0
        for pattern in patterns:
            for match in list(re.finditer(pattern, text, re.I))[:5]:
                start = max(0, match.start() - 180)
                end = min(len(text), match.end() + 260)
                snippet = " ".join(text[start:end].split())
                lines.append("MATCH: " + pattern)
                lines.append("CONTEXT: " + snippet)
                found += 1
        lines.append("CONTEXT_MATCHES: " + str(found))

    except Exception as exc:
        failed += 1
        lines.append("STATUS: FAILED")
        lines.append("ERROR: " + type(exc).__name__ + ": " + str(exc))

lines.append("\nFAILED_DOCUMENTS: " + str(failed))
lines.append("LEGAL_RECONCILIATION_COMPLETE: NO")
lines.append("COMPLIANCE_RULES_ACTIVATED: NO")
lines.append("DATABASE_MODIFIED: NO")
report.write_text("\n".join(lines), encoding="utf-8")

print("PHASE 2L REPORT:", report)
print("FAILED_DOCUMENTS:", failed)
print("REPORT_BYTES:", report.stat().st_size)
sys.exit(1 if failed else 0)
