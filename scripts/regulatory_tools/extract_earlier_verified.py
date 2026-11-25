import sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts/regulatory_tools/vendor").resolve()))
from pypdf import PdfReader
root = Path("data/regulatory/fssai/amendments")
for name in ["labelling_amendment_2022_10_11", "labelling_amendment_2025_08_08"]:
    pdf = root / (name + ".pdf")
    if not pdf.exists():
        print(name, "PDF_MISSING")
        continue
    output = root / (name + ".txt")
    if output.exists():
        print(name, "TEXT_ALREADY_EXISTS")
        continue
    try:
        reader = PdfReader(str(pdf))
        pages = ["===== PAGE {} =====\n{}".format(i, p.extract_text() or "") for i, p in enumerate(reader.pages, 1)]
        output.write_text("\n\n".join(pages), encoding="utf-8")
        low_text = sum(len(p.strip()) < 60 for p in pages)
        print(name, "PAGES", len(pages), "LOW_TEXT", low_text, "CHARS", sum(len(p) for p in pages))
    except Exception as exc:
        print(name, "EXTRACTION_FAILED", type(exc).__name__, str(exc))
