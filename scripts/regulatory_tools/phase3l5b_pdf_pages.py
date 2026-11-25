import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path.cwd()
inventory_path = root / "logs/regulatory_phase3l5_inventory.json"
report_path = root / "logs/regulatory_phase3l5b_pdf_report.txt"
output_path = root / "logs/regulatory_phase3l5b_pdf_pages.json"

messages = ["FOODINSIGHTAI PHASE 3L.5B - DOCKER PDF PAGE VERIFICATION"]

def log(value):
    messages.append(str(value))
    print(value, flush=True)

def save():
    report_path.write_text("\n".join(messages), encoding="utf-8")

if not inventory_path.is_file():
    raise SystemExit("Phase 3L.5 inventory is missing")

inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
amendments = inventory.get("amendments", [])

if len(amendments) != 6:
    raise SystemExit("Expected six amendment records")

compose = [
    "docker", "compose",
    "-f", "docker-compose.yml",
    "-f", "docker-compose.regulatory.yml",
]

probe = r'''
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader

base = Path("/app/data/regulatory/fssai")
registry = json.loads(
    (base / "labelling_amendments_consolidated_v1.json")
    .read_text(encoding="utf-8-sig")
)

def pdf_for(item):
    text = item["extracted_text_file"].replace("\\", "/")
    path = Path(text)
    options = [
        Path("/app") / path,
        base / path,
        base / "amendments/incoming" / path.name,
        base / "amendments" / path.name,
    ]
    for candidate in options:
        pdf = candidate.with_suffix(".pdf").resolve()
        if pdf.is_relative_to(base) and pdf.is_file():
            return pdf
    return None

def patterns_for(provision):
    regulation = re.fullmatch(
        r"Regulation\s+(\d+)", provision, re.I
    )
    if regulation:
        return [
            ("REGULATION_REFERENCE",
             r"\bregulation\s+" + regulation.group(1) + r"\b")
        ]

    schedule = re.match(r"Schedule[-\s]*([IVX]+)", provision, re.I)
    if schedule:
        roman = schedule.group(1)
        patterns = [
            ("SCHEDULE_REFERENCE",
             r"\bschedule\s*[-–]?\s*" + roman + r"\b")
        ]
        paragraph = re.search(
            r"paragraph\s+([\d.()]+)", provision, re.I
        )
        if paragraph:
            digits = paragraph.group(1)
            if re.fullmatch(r"\d+\.\d+", digits):
                number = re.escape(digits).replace(
                    r"\.", r"\s*\.\s*"
                )
            else:
                number = re.escape(digits).replace(
                    r"\(", r"\s*\(\s*"
                ).replace(r"\)", r"\s*\)")
            patterns.insert(
                0,
                ("PARAGRAPH_NUMBER_CANDIDATE",
                 r"(?<!\d)" + number + r"(?!\d)")
            )
        return patterns
    return [("REFERENCE_LITERAL", re.escape(provision))]

results = []
for item in registry["amendments"]:
    pdf = pdf_for(item)
    record = {
        "amendment_id": item["amendment_id"],
        "pdf_path": str(pdf) if pdf else None,
        "pdf_sha256": None,
        "pdf_page_count": None,
        "pdf_status": "NOT_FOUND" if pdf is None else "AVAILABLE",
        "provisions": [],
        "legal_review_complete": False,
        "compliance_verdict": None,
    }

    if pdf:
        record["pdf_sha256"] = hashlib.sha256(
            pdf.read_bytes()
        ).hexdigest()
        try:
            reader = PdfReader(str(pdf))
            pages = [
                (page.extract_text() or "")
                for page in reader.pages
            ]
            record["pdf_page_count"] = len(pages)
            record["pdf_status"] = "TEXT_SEARCHED"
        except Exception as exc:
            pages = []
            record["pdf_status"] = "EXTRACTION_FAILED"
            record["error_type"] = type(exc).__name__
    else:
        pages = []

    for provision in item["affected_provisions"]:
        matches = []
        for kind, expression in patterns_for(provision):
            for index, page_text in enumerate(pages):
                normalized = " ".join(page_text.split())
                found = re.search(
                    expression, normalized, re.IGNORECASE
                )
                if found:
                    matches.append({
                        "pdf_page": index + 1,
                        "match_method": kind,
                        "excerpt": normalized[
                            max(0, found.start() - 70):
                            found.end() + 170
                        ][:320],
                        "exact_clause_verified": False,
                    })

        # Candidate pages are search matches, not validated citations.
        unique = {}
        for found in matches:
            unique.setdefault(found["pdf_page"], found)

        record["provisions"].append({
            "provision_reference": provision,
            "page_candidates": list(unique.values())[:12],
            "exact_clause_verified": False,
            "effective_date_verified": False,
            "exceptions_reviewed": False,
            "supersession_reviewed": False,
            "product_applicability_verified": False,
            "compliance_verdict": None,
        })
    results.append(record)

print("PHASE3L5B_JSON_START")
print(json.dumps(results, ensure_ascii=False))
print("PHASE3L5B_JSON_END")
'''

try:
    check = subprocess.run(
        compose + ["ps", "-q", "backend"],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=30,
    )
    if check.returncode or not check.stdout.strip():
        raise RuntimeError("Backend container is not running")

    log("RUNNING_BACKEND: FOUND")

    result = subprocess.run(
        [
            "docker", "exec", "-i", check.stdout.strip(),
            "python", "-c", probe,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )

    if result.returncode:
        raise RuntimeError(
            "Docker PDF inspection failed: " +
            result.stderr[-2500:]
        )

    raw = result.stdout
    start_marker = "PHASE3L5B_JSON_START"
    end_marker = "PHASE3L5B_JSON_END"

    if start_marker not in raw or end_marker not in raw:
        raise RuntimeError("PDF inspection output missing markers")

    payload = raw.split(start_marker, 1)[1].split(
        end_marker, 1
    )[0].strip()

    records = json.loads(payload)
    expected = {
        item["amendment_id"]: item
        for item in amendments
    }

    if len(records) != 6:
        raise RuntimeError("Incomplete PDF inspection")

    verified_hashes = 0
    page_candidates = 0
    unresolved = 0

    for item in records:
        identifier = item["amendment_id"]
        original = expected[identifier]

        if item["pdf_sha256"] != original["pdf_sha256"]:
            raise RuntimeError(
                "PDF hash mismatch: " + identifier
            )
        verified_hashes += 1

        expected_provisions = set(
            original["affected_provisions"]
        )
        observed_provisions = {
            entry["provision_reference"]
            for entry in item["provisions"]
        }

        if expected_provisions != observed_provisions:
            raise RuntimeError(
                "Provision registry mismatch: " + identifier
            )

        for provision in item["provisions"]:
            count = len(provision["page_candidates"])
            page_candidates += count
            if count == 0:
                unresolved += 1

        log(
            identifier +
            " | pdf_pages=" + str(item["pdf_page_count"]) +
            " | status=" + item["pdf_status"] +
            " | provision_items=" + str(len(item["provisions"]))
        )

    result_document = {
        "schema_version": "1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "method": "PDF_TEXT_SEARCH_IN_RUNNING_BACKEND",
        "legal_review_complete": False,
        "compliance_rules_enabled": False,
        "pdf_hashes_verified": verified_hashes,
        "page_match_count": page_candidates,
        "provisions_without_page_candidates": unresolved,
        "amendments": records,
        "notice": (
            "PDF page matches are discovery candidates only. "
            "Exact legal wording, commencement, exemptions, "
            "supersession and product applicability remain unverified."
        ),
    }

    output_path.write_text(
        json.dumps(result_document, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    log("PDF_HASHES_VERIFIED: " + str(verified_hashes))
    log("PAGE_MATCH_CANDIDATES: " + str(page_candidates))
    log("PROVISIONS_WITHOUT_PAGE_CANDIDATES: " + str(unresolved))
    log("LEGAL_REVIEW_COMPLETE: NO")
    log("COMPLIANCE_RULES_ENABLED: NO")
    log("APPLICATION_CODE_MODIFIED: NO")
    log("DOCKER_REBUILD_REQUIRED: NO")
    log("STATUS: PASSED")
    log("OUTPUT: " + str(output_path))
    code = 0

except Exception as exc:
    log("STATUS: FAILED")
    log("ERROR: " + str(exc))
    code = 1

save()
log("REPORT: " + str(report_path))
sys.exit(code)
