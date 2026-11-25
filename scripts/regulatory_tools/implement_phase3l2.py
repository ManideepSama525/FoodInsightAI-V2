from pathlib import Path
from datetime import datetime, date
import ast
import shutil
import subprocess
import sys

root = Path.cwd()
screening = root / "backend/app/services/regulatory_label_screening.py"
service = root / "backend/app/services/regulatory_clause_preview.py"
test = root / "backend/tests/test_regulatory_phase3l2.py"
report = root / "logs/regulatory_phase3l2_report.txt"

notes = ["FOODINSIGHTAI PHASE 3L.2 - CLAUSE EVIDENCE MAPPING"]

def log(message):
    message = str(message)
    notes.append(message)
    print(message, flush=True)

def save():
    report.write_text("\n".join(notes), encoding="utf-8")

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected one anchor, found {count}"
        )
    return text.replace(old, new, 1)

service_source = '''"""Preliminary FSSAI provision-to-label evidence mapping.

Only existing registered amendments are considered.
These are provision candidates, NOT approved executable rules.
No compliance or violation decision may be produced.
"""

from backend.app.services.regulatory_registry import (
    load_amendment_registry,
)

# Discovery hints only. NOT legal obligations or predicates.
FIELD_HINTS = {
    "Regulation 5": ("nutrition_section",),
    "Regulation 6": ("allergens", "ingredients"),
    "Regulation 7": ("ingredients",),
    "Schedule-II paragraph 2.6": ("ingredients",),
    "Schedule-II paragraph 2.2": ("ingredients",),
}

def map_clause_evidence(
    screening_result: dict,
    label_fields: list,
) -> dict:
    registry = load_amendment_registry()

    if registry.get("compliance_rules_enabled") is not False:
        raise ValueError("Unapproved rule activation")

    if registry.get("legal_review_complete") is not False:
        raise ValueError("Unexpected legal approval state")

    amendments = {
        item["amendment_id"]: item
        for item in registry["amendments"]
    }

    observed = {
        item.get("field"): item
        for item in label_fields
        if isinstance(item, dict)
        and item.get("verification_status")
            == "EXTRACTED_UNVERIFIED"
    }

    candidates = []
    for candidate in screening_result.get(
        "candidate_amendments", []
    ):
        identifier = candidate.get("amendment_id")
        source = amendments.get(identifier)

        if source is None:
            raise ValueError("Unknown amendment reference")

        if source.get("compliance_rules_enabled") is not False:
            raise ValueError("Amendment is unexpectedly enabled")

        if (
            candidate.get("product_applicability_verified")
            is not False
        ):
            raise ValueError("Unsupported applicability approval")

        for provision in source.get("affected_provisions", []):
            hints = FIELD_HINTS.get(provision, ())
            evidence = []

            for field in hints:
                record = observed.get(field)
                if record:
                    evidence.append({
                        "field": field,
                        "value": record.get("value"),
                        "evidence_text": record.get("evidence_text"),
                        "line_number": record.get("line_number"),
                        "verification_status": "EXTRACTED_UNVERIFIED",
                    })

            candidates.append({
                "amendment_id": identifier,
                "provision_reference": provision,
                "date_status": candidate.get("date_status"),
                "source_text_sha256": source.get(
                    "extracted_text_sha256"
                ),
                "suggested_evidence_fields": list(hints),
                "extracted_evidence": evidence,
                "field_mapping_status": (
                    "PRELIMINARY_HINT"
                    if hints else "NOT_YET_MAPPED"
                ),
                "product_applicability_verified": False,
                "legal_review_status": "PENDING",
                "requirement_text_verified": False,
                "exceptions_checked": False,
                "supersession_checked": False,
                "rule_executed": False,
                "compliance_verdict": None,
                "finding_status": "NEEDS_LEGAL_REVIEW",
            })

    return {
        "provision_candidate_count": len(candidates),
        "provision_candidates": candidates,
        "legal_review_complete": False,
        "rule_execution_performed": False,
        "compliance_verdict": None,
        "notice": (
            "Provision references are discovery candidates. "
            "Field mappings are preliminary hints, not verified "
            "statutory requirements. Extracted label evidence "
            "is unverified. No legal compliance determination "
            "has been performed."
        ),
    }
'''

test_source = '''import unittest
from datetime import date

from backend.app.services.regulatory_product_screening import (
    screen_product,
)
from backend.app.services.regulatory_clause_preview import (
    map_clause_evidence,
)

class Phase3L2Tests(unittest.TestCase):
    def screening(self, category="bread"):
        return screen_product(category, date(2026, 11, 18))

    def fields(self):
        return [{
            "field": "ingredients",
            "value": "Wheat flour, sugar",
            "evidence_text": "INGREDIENTS: Wheat flour, sugar",
            "line_number": 5,
            "verification_status": "EXTRACTED_UNVERIFIED",
        }]

    def test_bread_provisions_found(self):
        result = map_clause_evidence(
            self.screening(), self.fields()
        )
        self.assertGreater(
            result["provision_candidate_count"], 0
        )

    def test_no_rule_execution(self):
        result = map_clause_evidence(
            self.screening(), self.fields()
        )
        self.assertFalse(result["rule_execution_performed"])
        self.assertIsNone(result["compliance_verdict"])

    def test_provision_sources_retained(self):
        result = map_clause_evidence(
            self.screening(), self.fields()
        )
        for item in result["provision_candidates"]:
            self.assertEqual(
                len(item["source_text_sha256"]), 64
            )
            self.assertTrue(item["amendment_id"])

    def test_original_label_evidence_retained(self):
        result = map_clause_evidence(
            self.screening(), self.fields()
        )
        evidence = [
            e
            for item in result["provision_candidates"]
            for e in item["extracted_evidence"]
        ]
        self.assertTrue(
            any(e["line_number"] == 5 for e in evidence)
        )

    def test_all_provisions_need_legal_review(self):
        result = map_clause_evidence(
            self.screening(), self.fields()
        )
        for item in result["provision_candidates"]:
            self.assertEqual(
                item["finding_status"], "NEEDS_LEGAL_REVIEW"
            )
            self.assertFalse(item["rule_executed"])
            self.assertIsNone(item["compliance_verdict"])

    def test_other_category_has_no_candidates(self):
        result = map_clause_evidence(
            self.screening("other"), self.fields()
        )
        self.assertEqual(
            result["provision_candidate_count"], 0
        )

    def test_unknown_amendment_rejected(self):
        screening = self.screening()
        screening["candidate_amendments"] = [{
            "amendment_id": "FAKE",
            "product_applicability_verified": False,
        }]
        with self.assertRaises(ValueError):
            map_clause_evidence(screening, [])

    def test_unverified_applicability_not_trusted(self):
        screening = self.screening()
        screening["candidate_amendments"][0][
            "product_applicability_verified"
        ] = True
        with self.assertRaises(ValueError):
            map_clause_evidence(screening, [])

    def test_invented_verified_field_is_ignored(self):
        fields = self.fields()
        fields[0]["verification_status"] = "VERIFIED"
        result = map_clause_evidence(
            self.screening(), fields
        )
        evidence = [
            e
            for item in result["provision_candidates"]
            for e in item["extracted_evidence"]
        ]
        self.assertEqual(len(evidence), 0)

if __name__ == "__main__":
    unittest.main()
'''

try:
    if not screening.is_file():
        raise RuntimeError("Phase 3J screening service missing")
    if service.exists() or test.exists():
        raise RuntimeError("Phase 3L.2 already partially installed")

    original = screening.read_text(encoding="utf-8-sig")
    if "PHASE_3L2_CLAUSE_MAPPING" in original:
        raise RuntimeError("Phase 3L.2 already integrated")

    anchor = '''    return {
        "product_type": product_type,
        "assessment_date": assessment_date.isoformat(),
        "document_type": document_kind,'''

    insertion = '''    # PHASE_3L2_CLAUSE_MAPPING
    from backend.app.services.regulatory_clause_preview import (
        map_clause_evidence,
    )
    try:
        clause_preview = map_clause_evidence(
            regulatory, extracted_fields
        )
    except ValueError as exc:
        # Clause mapping is supplementary. Never promote an
        # unknown amendment into a trusted legal rule.
        # Preserve the existing evidence assessment and make
        # the mapping failure explicit.
        clause_preview = {
            "status": "UNAVAILABLE_NEEDS_REVIEW",
            "provision_candidate_count": 0,
            "provision_candidates": [],
            "legal_review_complete": False,
            "rule_execution_performed": False,
            "compliance_verdict": None,
            "notice": (
                "Clause mapping unavailable: "
                + str(exc)
                + ". No compliance decision was made."
            ),
        }

'''

    updated = replace_once(
        original,
        anchor,
        insertion + anchor,
        "Clause mapping integration",
    )

    updated = replace_once(
        updated,
        '''        "findings": findings,''',
        '''        "findings": findings,
        "clause_preview": clause_preview,''',
        "Assessment response integration",
    )

    ast.parse(service_source)
    ast.parse(test_source)
    ast.parse(updated)

except Exception as exc:
    log("STATUS: FAILED_BEFORE_CHANGES")
    log("ERROR: " + str(exc))
    save()
    sys.exit(1)

backup = screening.with_name(
    "regulatory_label_screening_before_3l2_"
    + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    + ".py"
)
shutil.copy2(screening, backup)
log("BACKUP: " + str(backup))

try:
    service.write_text(service_source, encoding="utf-8")
    test.write_text(test_source, encoding="utf-8")
    screening.write_text(updated, encoding="utf-8")

    checks = [
        (
            "PYTHON_COMPILE",
            [
                sys.executable, "-m", "py_compile",
                str(screening), str(service), str(test),
            ],
        ),
        (
            "PHASE_3L2_TESTS",
            [
                sys.executable, "-m", "unittest",
                "discover", "-s", "backend/tests",
                "-p", "test_regulatory_phase3l2.py", "-v",
            ],
        ),
        (
            "PHASE_3J_REGRESSION",
            [
                sys.executable, "-m", "unittest",
                "discover", "-s", "backend/tests",
                "-p", "test_regulatory_phase3j.py", "-v",
            ],
        ),
    ]

    for label, command in checks:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        log(label + "_EXIT_CODE: " + str(result.returncode))
        log((result.stdout + chr(10) + result.stderr)[-6000:])
        if result.returncode:
            raise RuntimeError(label + " failed")

    log("STATUS: PASSED")
    log("PROVISION_MAPPING: IMPLEMENTED")
    log("EXISTING_RULE_ENGINE: PRESERVED")
    log("LEGAL_RULE_EXECUTION: DISABLED")
    log("COMPLIANCE_VERDICTS: DISABLED")
    log("FRONTEND_MODIFIED: NO")
    log("DATABASE_MODIFIED: NO")
    log("DOCKER_REBUILD_REQUIRED: YES")

except Exception as exc:
    shutil.copy2(backup, screening)
    service.unlink(missing_ok=True)
    test.unlink(missing_ok=True)
    log("STATUS: FAILED_AND_ROLLED_BACK")
    log("ERROR: " + str(exc))
    log("ORIGINAL_SCREENING_SERVICE_RESTORED: YES")
    save()
    sys.exit(1)

save()
log("REPORT: " + str(report))
