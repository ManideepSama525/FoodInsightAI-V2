"""Phase 3L.5: read-only FSSAI source reconciliation inventory.

Source matches are discovery evidence, not legal approval.
No application or registry source files are modified.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd().resolve()
DATA = ROOT / "data/regulatory/fssai"
OUT = ROOT / "logs"
OUT.mkdir(parents=True, exist_ok=True)

REPORT = OUT / "regulatory_phase3l5_report.txt"
INVENTORY = OUT / "regulatory_phase3l5_inventory.json"
log = ["FOODINSIGHTAI PHASE 3L.5 - LEGAL SOURCE RECONCILIATION"]
issues = []

def note(message):
    log.append(str(message))
    print(message, flush=True)

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def read_json(name):
    path = DATA / name
    if not path.is_file():
        raise RuntimeError("Missing required registry: " + name)
    return json.loads(path.read_text(encoding="utf-8-sig"))

def trusted_local_path(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw.replace("\\", "/"))
    alternatives = [
        ROOT / candidate,
        DATA / candidate,
        DATA / "amendments" / candidate,
        DATA / "amendments" / "incoming" / candidate.name,
    ]
    for path in alternatives:
        resolved = path.resolve()
        if (
            resolved.is_relative_to(ROOT)
            and resolved.is_file()
        ):
            return resolved
    return None

def relative(path):
    return str(path.relative_to(ROOT)).replace("\\", "/")

def text_candidate(text, provision):
    """Locate literal provision text. Never infer a clause."""
    if not isinstance(provision, str) or not provision:
        return None
    expression = re.escape(provision)
    match = re.search(expression, text, re.IGNORECASE)
    if not match:
        return None
    line = text.count("\n", 0, match.start()) + 1
    excerpt = " ".join(
        text[max(0, match.start()-90):match.end()+230].split()
    )
    return {
        "extracted_text_line": line,
        "matching_excerpt": excerpt[:400],
        "match_type": "LITERAL_REFERENCE_ONLY",
        "clause_wording_verified": False,
    }

def pdf_page_candidates(pdf, provision, PdfReader):
    if pdf is None or PdfReader is None:
        return {
            "page_candidates": [],
            "pdf_search_status": "NOT_AVAILABLE",
        }
    try:
        reader = PdfReader(str(pdf))
        pages = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if re.search(
                re.escape(provision), text, re.IGNORECASE
            ):
                pages.append(index + 1)
        return {
            "page_candidates": pages[:12],
            "pdf_search_status": (
                "LITERAL_MATCH_CANDIDATES"
                if pages else "NO_LITERAL_MATCH"
            ),
        }
    except Exception as exc:
        return {
            "page_candidates": [],
            "pdf_search_status": "EXTRACTION_FAILED",
            "extraction_error_type": type(exc).__name__,
        }

inventory = {
    "schema_version": "1.0",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "authority": "FSSAI",
    "jurisdiction": "India",
    "inventory_type": "SOURCE_DISCOVERY_NOT_LEGAL_APPROVAL",
    "compliance_rules_enabled": False,
    "legal_review_complete": False,
    "amendments": [],
    "reference_regulations": [],
    "reference_schedules": [],
    "review_queue": [],
}

try:
    registry = read_json("labelling_amendments_consolidated_v1.json")
    references = read_json("labelling_regulation_text_v1.json")
    schedules = read_json("labelling_schedules_v1.json")

    assert registry["compliance_rules_enabled"] is False
    assert registry["legal_review_complete"] is False

    amendments = registry["amendments"]
    if len(amendments) != 6:
        raise RuntimeError("Unexpected amendment count")

    try:
        from pypdf import PdfReader
        note("PYPDF_AVAILABLE: YES")
    except ImportError:
        PdfReader = None
        note("PYPDF_AVAILABLE: NO; PDF page search skipped")

    note("=== AMENDMENT EVIDENCE ===")

    for amendment in amendments:
        amendment_id = amendment["amendment_id"]
        raw_path = amendment.get("extracted_text_file")
        text_path = trusted_local_path(raw_path)
        expected_hash = amendment.get("extracted_text_sha256")

        record = {
            "amendment_id": amendment_id,
            "notification_date": amendment.get("notification_date"),
            "claimed_effective_date": amendment.get("effective_date"),
            "effective_date_verification":
                amendment.get("effective_date_verification"),
            "affected_provisions":
                amendment.get("affected_provisions", []),
            "text_file": (
                relative(text_path) if text_path else None
            ),
            "text_file_sha256": None,
            "registered_text_sha256": expected_hash,
            "text_hash_matches_registry": False,
            "pdf_file": None,
            "pdf_sha256": None,
            "provision_matches": [],
            "legal_review_complete": False,
            "compliance_rules_enabled": False,
        }

        if text_path:
            actual_hash = digest(text_path)
            record["text_file_sha256"] = actual_hash
            record["text_hash_matches_registry"] = (
                actual_hash.lower() ==
                str(expected_hash or "").lower()
            )
            source_text = text_path.read_text(
                encoding="utf-8-sig", errors="replace"
            )

            pdf_path = text_path.with_suffix(".pdf")
            if pdf_path.is_file():
                record["pdf_file"] = relative(pdf_path)
                record["pdf_sha256"] = digest(pdf_path)
            else:
                pdf_path = None
        else:
            source_text = ""
            pdf_path = None
            issues.append(amendment_id + ": source text missing")

        if not record["text_hash_matches_registry"]:
            issues.append(
                amendment_id + ": source hash mismatch or unavailable"
            )

        for provision in record["affected_provisions"]:
            match = text_candidate(source_text, provision)
            pdf_match = pdf_page_candidates(
                pdf_path, provision, PdfReader
            )
            entry = {
                "provision_reference": provision,
                "text_reference_match": match,
                **pdf_match,
                "exact_clause_verified": False,
                "legal_applicability_verified": False,
                "exceptions_reviewed": False,
                "supersession_reviewed": False,
                "legal_verdict": None,
            }
            record["provision_matches"].append(entry)
            inventory["review_queue"].append({
                "amendment_id": amendment_id,
                "provision_reference": provision,
                "priority": (
                    "SOURCE_INTEGRITY"
                    if not record["text_hash_matches_registry"]
                    else "LEGAL_REVIEW"
                ),
                "required_checks": [
                    "Verify official notification and exact clause text",
                    "Verify legal effective and compliance dates",
                    "Check exemptions and transitional provisions",
                    "Check later amendments, orders and directions",
                    "Verify product-category applicability",
                ],
                "review_complete": False,
            })

        inventory["amendments"].append(record)
        note(
            f"{amendment_id}: hash_match="
            f"{record['text_hash_matches_registry']}, "
            f"provisions={len(record['provision_matches'])}, "
            f"pdf={'YES' if pdf_path else 'NO'}"
        )

    note("=== REFERENCE COMPENDIUM ===")
    for item in references.get("regulations", []):
        inventory["reference_regulations"].append({
            "regulation_number": item.get("regulation_number"),
            "chapter": item.get("chapter"),
            "heading": item.get("heading"),
            "candidate_start_page": item.get("start_page"),
            "candidate_end_page": item.get("end_page"),
            "reference_source_sha256":
                references.get("source_pdf_sha256"),
            "reference_kind": "COMPENDIUM",
            "amendments_reconciled": False,
            "exact_clause_verified": False,
            "legal_status": "PENDING_REVIEW",
        })

    for item in schedules.get("schedules", []):
        inventory["reference_schedules"].append({
            "schedule_id": item.get("schedule_id"),
            "candidate_start_page": item.get("start_page"),
            "candidate_end_page": item.get("end_page"),
            "reference_kind": "COMPENDIUM",
            "amendments_reconciled": False,
            "exact_clause_verified": False,
            "legal_status": "PENDING_REVIEW",
        })

    reference_pdf = DATA / "fssai_labelling_display_2025_reference.pdf"
    if reference_pdf.is_file():
        actual_pdf_hash = digest(reference_pdf)
        expected_pdf_hash = references.get("source_pdf_sha256")
        inventory["reference_pdf_integrity"] = {
            "path": relative(reference_pdf),
            "sha256": actual_pdf_hash,
            "registry_sha256": expected_pdf_hash,
            "hash_matches": actual_pdf_hash.lower() ==
                            str(expected_pdf_hash or "").lower(),
        }
        if not inventory["reference_pdf_integrity"]["hash_matches"]:
            issues.append("Reference PDF hash mismatch")
    else:
        issues.append("Reference PDF missing")

    inventory["integrity_issues"] = issues

    # The inventory cannot grant legal approval or activate rules.
    assert inventory["compliance_rules_enabled"] is False
    assert inventory["legal_review_complete"] is False
    assert all(
        record["compliance_rules_enabled"] is False
        for record in inventory["amendments"]
    )
    assert all(
        provision["legal_verdict"] is None
        for record in inventory["amendments"]
        for provision in record["provision_matches"]
    )

    INVENTORY.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    reloaded = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert len(reloaded["amendments"]) == 6
    assert len(reloaded["reference_regulations"]) == 13
    assert len(reloaded["reference_schedules"]) == 2

    note("AMENDMENTS: 6")
    note("REFERENCE_REGULATIONS: 13")
    note("REFERENCE_SCHEDULES: 2")
    note(
        "PROVISION_REVIEW_ITEMS: "
        + str(len(reloaded["review_queue"]))
    )
    note("INTEGRITY_ISSUES: " + str(len(issues)))
    for issue in issues:
        note("ISSUE: " + issue)

    note("LEGAL_REVIEW_COMPLETE: NO")
    note("COMPLIANCE_RULES_ENABLED: NO")
    note("APPLICATION_CODE_MODIFIED: NO")
    note("DATABASE_MODIFIED: NO")
    note("DOCKER_REBUILD_REQUIRED: NO")
    note("STATUS: PASSED_WITH_REVIEW_ITEMS"
         if issues else "STATUS: PASSED")
    note("INVENTORY: " + str(INVENTORY))

except Exception as exc:
    note("STATUS: FAILED")
    note("ERROR: " + repr(exc))
    REPORT.write_text("\n".join(log), encoding="utf-8")
    sys.exit(1)

REPORT.write_text("\n".join(log), encoding="utf-8")
note("REPORT: " + str(REPORT))
