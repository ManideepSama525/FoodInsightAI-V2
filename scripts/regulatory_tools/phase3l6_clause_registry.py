"""Phase 3L.6: build a non-executable legal clause review registry."""
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path.cwd()
source_inventory = root / "logs/regulatory_phase3l5_inventory.json"
pdf_inventory = root / "logs/regulatory_phase3l5b_pdf_pages.json"

output = root / "logs/regulatory_phase3l6_clause_registry.json"
report = root / "logs/regulatory_phase3l6_report.txt"

messages = ["FOODINSIGHTAI PHASE 3L.6 - CONTROLLED CLAUSE REVIEW REGISTRY"]

def note(value):
    messages.append(str(value))
    print(value, flush=True)

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load(path):
    if not path.is_file():
        raise RuntimeError("Missing required inventory: " + str(path))
    return json.loads(path.read_text(encoding="utf-8-sig"))

def validate_registry(data):
    assert data["legal_review_complete"] is False
    assert data["compliance_rules_enabled"] is False
    assert data["rule_execution_enabled"] is False
    assert data["compliance_verdict"] is None
    assert len(data["clauses"]) == 15

    identifiers = set()
    for clause in data["clauses"]:
        assert clause["clause_id"] not in identifiers
        identifiers.add(clause["clause_id"])

        assert clause["source_pdf_sha256"]
        assert len(clause["source_pdf_sha256"]) == 64
        assert clause["review_status"] == "PENDING_LEGAL_REVIEW"
        assert clause["exact_clause_verified"] is False
        assert clause["effective_date_verified"] is False
        assert clause["exceptions_checked"] is False
        assert clause["supersession_checked"] is False
        assert clause["product_applicability_verified"] is False
        assert clause["rule_enabled"] is False
        assert clause["compliance_verdict"] is None
        assert clause["candidate_pages"]

        total_pages = clause["source_pdf_page_count"]
        for candidate in clause["candidate_pages"]:
            assert isinstance(candidate["pdf_page"], int)
            assert 1 <= candidate["pdf_page"] <= total_pages
            assert candidate["citation_verified"] is False
            assert candidate["match_class"] in (
                "REFERENCE_MATCH",
                "BROAD_PARAGRAPH_MATCH",
            )

    assert data["clause_count"] == len(data["clauses"])
    return True

def main():
    previous = load(source_inventory)
    pdf_data = load(pdf_inventory)

    if output.exists():
        raise RuntimeError(
            "Phase 3L.6 output exists; refusing to overwrite"
        )

    if (
        previous.get("legal_review_complete") is not False
        or previous.get("compliance_rules_enabled") is not False
        or pdf_data.get("legal_review_complete") is not False
        or pdf_data.get("compliance_rules_enabled") is not False
    ):
        raise RuntimeError("Unexpected prior legal activation")

    source_by_id = {
        item["amendment_id"]: item
        for item in previous["amendments"]
    }

    if len(source_by_id) != 6:
        raise RuntimeError("Source registry must have six amendments")

    clauses = []
    broad_matches = 0
    sources_checked = set()

    for pdf_record in pdf_data["amendments"]:
        identifier = pdf_record["amendment_id"]
        source = source_by_id.get(identifier)

        if source is None:
            raise RuntimeError("Unknown amendment: " + identifier)

        if pdf_record["pdf_sha256"] != source["pdf_sha256"]:
            raise RuntimeError("PDF inventory hash mismatch")

        if not source["text_hash_matches_registry"]:
            raise RuntimeError("Untrusted extracted text hash")

        # Verify physical PDFs and extracted texts have not changed
        # since inventory generation.
        source_pdf = root / source["pdf_file"]
        source_txt = root / source["text_file"]

        for path in (source_pdf, source_txt):
            if not path.is_file():
                raise RuntimeError("Missing local source: " + str(path))

        if sha256(source_pdf) != source["pdf_sha256"]:
            raise RuntimeError("Physical PDF changed")

        if sha256(source_txt) != source["text_file_sha256"]:
            raise RuntimeError("Physical extracted text changed")

        sources_checked.add(identifier)

        expected = set(source["affected_provisions"])
        actual = {
            entry["provision_reference"]
            for entry in pdf_record["provisions"]
        }

        if expected != actual:
            raise RuntimeError("Provision mismatch: " + identifier)

        for index, provision in enumerate(
            pdf_record["provisions"], 1
        ):
            reference = provision["provision_reference"]
            page_count = pdf_record["pdf_page_count"]

            if not isinstance(page_count, int) or page_count < 1:
                raise RuntimeError("Invalid source page count")

            page_candidates = []
            for candidate in provision["page_candidates"]:
                method = candidate["match_method"]
                match_class = (
                    "BROAD_PARAGRAPH_MATCH"
                    if method == "PARAGRAPH_NUMBER_CANDIDATE"
                    else "REFERENCE_MATCH"
                )

                if match_class == "BROAD_PARAGRAPH_MATCH":
                    broad_matches += 1

                page_candidates.append({
                    "pdf_page": candidate["pdf_page"],
                    "match_method": method,
                    "match_class": match_class,
                    "excerpt": candidate.get("excerpt", ""),
                    "citation_verified": False,
                    "provision_text_verified": False,
                })

            if not page_candidates:
                raise RuntimeError(
                    "Missing page candidate: " + reference
                )

            clause_id = (
                identifier + "-CLAUSE-" + str(index).zfill(2)
            )

            clauses.append({
                "clause_id": clause_id,
                "amendment_id": identifier,
                "provision_reference": reference,
                "notification_date":
                    source.get("notification_date"),
                "claimed_effective_date":
                    source.get("claimed_effective_date"),
                "source_pdf_path": source["pdf_file"],
                "source_pdf_sha256": source["pdf_sha256"],
                "source_pdf_page_count": page_count,
                "source_text_path": source["text_file"],
                "source_text_sha256":
                    source["text_file_sha256"],
                "candidate_pages": page_candidates,
                "authoritative_pdf_page": None,
                "authoritative_clause_text": None,
                "exact_clause_verified": False,
                "effective_date_verified": False,
                "exceptions_checked": False,
                "supersession_checked": False,
                "product_applicability_verified": False,
                "review_status": "PENDING_LEGAL_REVIEW",
                "rule_enabled": False,
                "compliance_verdict": None,
                "review_tasks": [
                    "Confirm exact provision wording against original PDF",
                    "Confirm English/Hindi and publication references",
                    "Confirm commencement and compliance dates",
                    "Check exemptions and transitional provisions",
                    "Check later amendments and implementation orders",
                    "Confirm product applicability and required facts",
                ],
            })

    if len(sources_checked) != 6:
        raise RuntimeError("Not all amendment PDFs were checked")

    result = {
        "schema_version": "1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "registry_type": "LEGAL_SOURCE_REVIEW_ONLY",
        "authority": "FSSAI",
        "jurisdiction": "India",
        "clause_count": len(clauses),
        "source_amendment_count": len(sources_checked),
        "legal_review_complete": False,
        "compliance_rules_enabled": False,
        "rule_execution_enabled": False,
        "compliance_verdict": None,
        "clauses": clauses,
        "notice": (
            "Candidate PDF locations are not verified legal "
            "citations. No clause is approved for automated "
            "regulatory compliance decisions."
        ),
    }

    validate_registry(result)

    # Negative safety tests: deliberately corrupt a temporary
    # copy and verify the validator rejects the alteration.
    for description, mutation in [
        ("Illegal rule activation",
         lambda item: item.update(
             {"compliance_rules_enabled": True}
         )),
        ("False clause approval",
         lambda item: item["clauses"][0].update(
             {"exact_clause_verified": True}
         )),
        ("Invented compliance verdict",
         lambda item: item["clauses"][0].update(
             {"compliance_verdict": "COMPLIANT"}
         )),
        ("Invalid PDF citation",
         lambda item: item["clauses"][0]["candidate_pages"][0]
         .update({"pdf_page": 99999})),
    ]:
        corrupted = copy.deepcopy(result)
        mutation(corrupted)
        try:
            validate_registry(corrupted)
        except AssertionError:
            note("NEGATIVE_TEST_PASSED: " + description)
        else:
            raise RuntimeError(
                "Safety validator accepted: " + description
            )

    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    validate_registry(load(output))

    note("SOURCE_PDFS_VALIDATED: 6")
    note("CLAUSE_RECORDS_CREATED: " + str(len(clauses)))
    note("BROAD_PARAGRAPH_MATCHES: " + str(broad_matches))
    note("AUTHORITATIVE_PAGES_APPROVED: 0")
    note("LEGAL_CLAUSES_APPROVED: 0")
    note("AUTOMATED_COMPLIANCE_RULES_ENABLED: 0")
    note("NEGATIVE_SAFETY_TESTS: 4 PASSED")
    note("APPLICATION_CODE_MODIFIED: NO")
    note("DATABASE_MODIFIED: NO")
    note("DOCKER_REBUILD_REQUIRED: NO")
    note("STATUS: PASSED")
    note("REGISTRY: " + str(output))

try:
    main()
    code = 0
except Exception as exc:
    note("STATUS: FAILED")
    note("ERROR: " + repr(exc))
    code = 1

report.write_text("\n".join(messages), encoding="utf-8")
note("REPORT: " + str(report))
sys.exit(code)
