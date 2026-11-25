import hashlib
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path("scripts/regulatory_tools/vendor").resolve()))
from pypdf import PdfReader

INDEX = "https://fssai.gov.in/food-law/regulations/amendments/labelling-display"
ROOT = Path("data/regulatory/fssai/amendments")
REPORT = Path("logs/regulatory_phase2k_report.txt")
ROOT.mkdir(parents=True, exist_ok=True)

EXPECTED = [
    (1, 10, "September", 2021),
    (2, 9, "September", 2022),
    (3, 11, "October", 2022),
    (4, 8, "August", 2025),
]

class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts = []
        self.links = []
        self.rows = []
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.depth += 1
            if self.depth == 1:
                self.parts, self.links = [], []
        if self.depth and tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == "tr" and self.depth:
            self.depth -= 1
            if self.depth == 0:
                self.rows.append((" ".join(self.parts), self.links[:]))

lines = ["FOODINSIGHTAI PHASE 2K - EARLIER AMENDMENTS", "INDEX: " + INDEX]
failures = 0

try:
    request = urllib.request.Request(INDEX, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        page = response.read().decode("utf-8", errors="replace")
    parser = Rows()
    parser.feed(page)
    lines.append("INDEX_ROWS_FOUND: " + str(len(parser.rows)))

    for number, day, month, year in EXPECTED:
        identifier = "FSSAI-LABEL-AMEND-" + str(number)
        date_pattern = rf"\b0?{day}(?:st|nd|rd|th)?\s+{month}\s*,?\s*{year}\b"
        matches = [(t, h) for t, h in parser.rows if re.search(date_pattern, " ".join(t.split()), re.I)]
        lines.append("")
        lines.append("DOCUMENT: " + identifier)
        lines.append("DATE_MATCHED_ROWS: " + str(len(matches)))
        if len(matches) != 1:
            failures += 1
            lines.append("STATUS: DATE_MATCH_UNRESOLVED")
            continue
        hrefs = matches[0][1]
        pdf_links = [x for x in hrefs if ".pdf" in x.lower()]
        if len(pdf_links) != 1:
            failures += 1
            lines.append("STATUS: PDF_LINK_UNRESOLVED")
            lines.append("ROW_LINKS: " + repr(hrefs))
            continue
        url = urljoin(INDEX, pdf_links[0])
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (host == "fssai.gov.in" or host.endswith(".fssai.gov.in")):
            failures += 1
            lines.append("STATUS: UNAPPROVED_DOWNLOAD_HOST")
            continue
        path = ROOT / ("labelling_amendment_{}_{}_{}.pdf".format(year, month.lower(), day))
        lines.append("SOURCE_URL: " + url)
        try:
            if path.exists():
                data = path.read_bytes()
                lines.append("EXISTING_FILE_REUSED: YES")
            else:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    data = response.read()
                if len(data) < 1000 or not data.startswith(b"%PDF-"):
                    raise ValueError("Downloaded content failed PDF validation")
                path.write_bytes(data)
                lines.append("EXISTING_FILE_REUSED: NO")
            if len(data) < 1000 or not data.startswith(b"%PDF-"):
                raise ValueError("Local PDF validation failed")
            reader = PdfReader(str(path))
            sections = []
            low_text = []
            for i, page_obj in enumerate(reader.pages, 1):
                extracted = page_obj.extract_text() or ""
                sections.append("===== PAGE {} =====\n{}".format(i, extracted))
                if len(extracted.strip()) < 40:
                    low_text.append(i)
            destination = path.with_suffix(".txt")
            if destination.exists():
                raise FileExistsError("Text output already exists: " + str(destination))
            destination.write_text("\n\n".join(sections), encoding="utf-8")
            lines.append("STATUS: EXTRACTED")
            lines.append("PAGES: " + str(len(reader.pages)))
            lines.append("PDF_SHA256: " + hashlib.sha256(data).hexdigest())
            lines.append("TEXT_CHARACTERS: " + str(sum(map(len, sections))))
            lines.append("LOW_TEXT_PAGES: " + str(low_text))
            lines.append("PDF: " + str(path))
            lines.append("TEXT: " + str(destination))
        except Exception as exc:
            failures += 1
            lines.append("STATUS: FAILED")
            lines.append("ERROR: " + type(exc).__name__ + ": " + str(exc))
except Exception as exc:
    failures += 1
    lines.append("DIRECTORY_ACCESS_ERROR: " + type(exc).__name__ + ": " + str(exc))

lines.append("")
lines.append("FAILED_DOCUMENTS: " + str(failures))
lines.append("LEGAL_RECONCILIATION_COMPLETE: NO")
lines.append("COMPLIANCE_RULES_ACTIVATED: NO")
lines.append("DATABASE_MODIFIED: NO")
REPORT.write_text("\n".join(lines), encoding="utf-8")
print("REPORT:", REPORT)
print("FAILED_DOCUMENTS:", failures)
sys.exit(1 if failures else 0)
