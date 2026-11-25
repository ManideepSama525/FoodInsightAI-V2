import sys
import hashlib
import logging
from pathlib import Path

vendor = Path("scripts/regulatory_tools/vendor").resolve()
sys.path.insert(0, str(vendor))
from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.WARNING)

root = Path("data/regulatory/fssai/amendments")
documents = [
    ("FSSAI-LABEL-AMEND-5", "labelling_amendment_2026_03_24.pdf"),
    ("FSSAI-LABEL-AMEND-6", "labelling_amendment_2026_11_06.pdf"),
]

print("FOODINSIGHTAI PHASE 2H - AMENDMENT EXTRACTION", flush=True)
print("=" * 65, flush=True)

failed = 0

for doc_id, filename in documents:
    pdf = root / filename
    print("\nDOCUMENT:", doc_id, flush=True)
    print("FILE:", pdf, flush=True)

    try:
        if not pdf.is_file():
            raise RuntimeError("PDF file missing")

        data = pdf.read_bytes()
        if len(data) < 1000 or not data.startswith(b"%PDF-"):
            raise RuntimeError("Invalid PDF file or signature")

        reader = PdfReader(str(pdf))
        pages = []
        low_text_pages = []

        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append("===== PAGE {} =====\n{}".format(index, text))
            if len(text.strip()) < 40:
                low_text_pages.append(index)

        output = pdf.with_suffix(".txt")
        output.write_text("\n\n".join(pages), encoding="utf-8")

        print("STATUS: EXTRACTED")
        print("PAGES:", len(reader.pages))
        print("FILE_BYTES:", len(data))
        print("SHA256:", hashlib.sha256(data).hexdigest())
        print("TOTAL_TEXT_CHARACTERS:", sum(len(p) for p in pages))
        print("LOW_TEXT_PAGES:", low_text_pages)
        print("EXTRACTED_TEXT:", output)

        for index, page in enumerate(pages[:2], start=1):
            print("PAGE_{}_PREVIEW:".format(index))
            print(page[:2200])

        if low_text_pages:
            print("WARNING: Some pages may need visual review.")

    except Exception as exc:
        failed += 1
        print("STATUS: FAILED")
        print("ERROR:", type(exc).__name__, str(exc))

    print("=" * 65, flush=True)

print("DOCUMENTS_FAILED:", failed)
print("LEGAL_AMENDMENTS_RECONCILED: NO")
print("COMPLIANCE_RULES_ACTIVATED: NO")
print("DATABASE_MODIFIED: NO")
sys.exit(1 if failed else 0)
