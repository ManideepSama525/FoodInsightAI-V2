from pathlib import Path
from datetime import datetime
import ast
import shutil
import subprocess
import sys

root = Path.cwd()
route = root / "backend/app/api/routes/regulatory.py"
api = root / "frontend/src/lib/api.ts"
panel = root / "frontend/src/app/RegulatoryCompliancePanel.tsx"
service = root / "backend/app/services/regulatory_label_screening.py"
tests = root / "backend/tests/test_regulatory_phase3j.py"
report = root / "logs/regulatory_phase3j_report.txt"
backup = root / "backups" / (
    "regulatory_phase3j_" +
    datetime.now().strftime("%Y%m%d_%H%M%S_%f")
)

existing = [route, api, panel]
created = [service, tests]
notes = ["FOODINSIGHTAI PHASE 3J - REGULATORY LABEL SCREENING"]

def log(message):
    message = str(message)
    notes.append(message)
    print(message, flush=True)

def save():
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(notes), encoding="utf-8")

def replace_once(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            label + ": expected one anchor, found " + str(count)
        )
    return source.replace(old, new, 1)

service_source = r'''"""Evidence-grounded preliminary product-label screening.

This module DOES NOT determine legal compliance.
OCR-derived fields are never automatically verified.
"""

import re
from datetime import date

from backend.app.services.regulatory_product_screening import (
    screen_product,
)

REVIEW_FIELDS = (
    "ingredients",
    "allergens",
    "nutrition_section",
    "fssai_licence_number",
    "net_quantity",
    "manufacture_date",
    "best_before",
    "expiry_date",
)

GAZETTE_MARKERS = (
    "gazette of india",
    "ministry of health and family welfare",
    "food safety and standards authority of india",
    "extraordinary part ii",
)


def assess_label_evidence(
    document: dict,
    product_type: str,
    assessment_date: date,
) -> dict:
    label_data = document.get("label_fields") or {}
    extracted_fields = label_data.get("fields") or []
    source_text = document.get("extracted_text") or ""

    field_map = {
        item["field"]: item
        for item in extracted_fields
        if item.get("field") in REVIEW_FIELDS
    }

    normalized = " ".join(source_text.lower().split())
    gazette_markers_found = [
        marker for marker in GAZETTE_MARKERS
        if marker in normalized
    ]

    appears_regulatory_source = (
        bool(gazette_markers_found)
        and len(field_map) < 2
    )

    document_kind = (
        "POSSIBLE_REGULATORY_NOTIFICATION"
        if appears_regulatory_source
        else "POSSIBLE_PRODUCT_LABEL"
        if len(field_map) >= 2
        else "DOCUMENT_TYPE_UNCERTAIN"
    )

    findings = []

    for field in REVIEW_FIELDS:
        evidence = field_map.get(field)

        if evidence is None:
            findings.append({
                "field": field,
                "status": "NOT_DETECTED",
                "severity": "INFORMATION_GAP",
                "value": None,
                "evidence_text": None,
                "line_number": None,
                "message": (
                    "This declaration was not detected in the "
                    "extracted text. This is not evidence of a "
                    "legal violation or that the declaration "
                    "is absent from the original packaging."
                ),
            })
            continue

        status = "EXTRACTED_UNVERIFIED"
        message = (
            "Text candidate found. Confirm against the "
            "original product label."
        )

        if field == "fssai_licence_number":
            number = re.sub(r"\D", "", str(evidence["value"]))
            if len(number) != 14:
                status = "REQUIRES_MANUAL_VERIFICATION"
                message = (
                    "The extracted number does not have "
                    "the expected 14-digit format."
                )
            elif len(set(number)) == 1:
                status = "SUSPECTED_TEST_OR_PLACEHOLDER_VALUE"
                message = (
                    "The number appears to be a synthetic "
                    "placeholder. It has not been checked "
                    "against official licensing records."
                )

        findings.append({
            "field": field,
            "status": status,
            "severity": "REVIEW_REQUIRED",
            "value": evidence.get("value"),
            "evidence_text": evidence.get("evidence_text"),
            "line_number": evidence.get("line_number"),
            "message": message,
        })

    # Existing category screening supplies candidate amendments,
    # not proven product applicability.
    regulatory = screen_product(product_type, assessment_date)

    return {
        "product_type": product_type,
        "assessment_date": assessment_date.isoformat(),
        "document_type": document_kind,
        "document_type_verified": False,
        "document_sha256": document.get("sha256"),
        "text_extraction_status": document.get(
            "extraction_status", "UNKNOWN"
        ),
        "document_stored": False,
        "document_facts_verified": False,
        "assessment_complete": False,
        "legal_review_status": "PENDING",
        "compliance_verdict": None,
        "detected_field_count": len(field_map),
        "findings": findings,
        "potentially_relevant_amendments": regulatory.get(
            "candidate_amendments", []
        ),
        "candidate_amendment_count": regulatory.get(
            "candidate_count", 0
        ),
        "source_document_warning": (
            "This appears to be a regulatory publication, "
            "not a product packaging label."
            if appears_regulatory_source else None
        ),
        "notice": (
            "Preliminary evidence review only. These are "
            "extraction findings, not confirmed FSSAI "
            "violations or compliance determinations. "
            "Applicable clauses, exemptions, effective dates "
            "and later directions require legal review."
        ),
    }
'''

route_source = '''

# PHASE_3J_LABEL_SCREENING
from datetime import date as RegulatoryScreeningDate
from typing import Literal as RegulatoryLiteral
from fastapi import Form as RegulatoryForm


@router.post("/assessment/label-preview")
async def regulatory_label_assessment_preview(
    user: AuthenticatedUser,
    file: UploadFile = File(...),
    product_type: RegulatoryLiteral[
        "bread",
        "coffee_chicory",
        "milk_product",
        "edible_oil",
        "sweetener_product",
        "other",
    ] = RegulatoryForm(...),
    assessment_date: RegulatoryScreeningDate = RegulatoryForm(...),
):
    """Independent, authenticated, non-persistent label screening."""
    from backend.app.services.regulatory_document_extraction import (
        extract_regulatory_document,
    )
    from backend.app.services.regulatory_label_screening import (
        assess_label_evidence,
    )
    from backend.app.services.regulatory_registry import (
        RegistryUnavailable,
    )

    del user
    try:
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Document exceeds 8 MB",
            )

        document = extract_regulatory_document(
            file.filename or "", content
        )
        return assess_label_evidence(
            document, product_type, assessment_date
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc)
        ) from exc
    except RegistryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory registry unavailable",
        ) from exc
    finally:
        await file.close()
'''

tests_source = r'''import io
import unittest
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.routes.regulatory import router
from backend.app.core.auth import get_current_user
from backend.app.services.regulatory_label_screening import (
    assess_label_evidence,
)


def sample_document():
    return {
        "sha256": "test-document-sha",
        "extraction_status": "TEXT_EXTRACTED",
        "extracted_text": (
            "INGREDIENTS: Wheat flour, salt\n"
            "ALLERGENS: Contains wheat\n"
            "FSSAI Lic No: 00000000000000\n"
        ),
        "label_fields": {
            "fields": [
                {
                    "field": "ingredients",
                    "value": "Wheat flour, salt",
                    "evidence_text": "INGREDIENTS: Wheat flour, salt",
                    "line_number": 1,
                },
                {
                    "field": "allergens",
                    "value": "Contains wheat",
                    "evidence_text": "ALLERGENS: Contains wheat",
                    "line_number": 2,
                },
                {
                    "field": "fssai_licence_number",
                    "value": "00000000000000",
                    "evidence_text": "FSSAI Lic No: 00000000000000",
                    "line_number": 3,
                },
            ],
        },
    }


def fake_regulatory_screen(product_type, assessment_date):
    return {
        "candidate_count": 1,
        "candidate_amendments": [
            {
                "amendment_id": "TEST-AMENDMENT",
                "date_status": "NEEDS_REVIEW",
                "affected_provisions": [],
                "compliance_verdict": None,
            }
        ],
        "compliance_verdict": None,
    }


class Phase3JTests(unittest.TestCase):

    def assess(self, document=None):
        with patch(
            "backend.app.services.regulatory_label_screening.screen_product",
            side_effect=fake_regulatory_screen,
        ):
            return assess_label_evidence(
                document if document is not None else sample_document(),
                "bread",
                date(2026, 11, 18),
            )

    def test_source_evidence_is_preserved(self):
        result = self.assess()
        item = next(
            item for item in result["findings"]
            if item["field"] == "ingredients"
        )
        self.assertEqual(
            item["evidence_text"],
            "INGREDIENTS: Wheat flour, salt",
        )
        self.assertEqual(item["line_number"], 1)

    def test_placeholder_licence_flagged(self):
        result = self.assess()
        item = next(
            item for item in result["findings"]
            if item["field"] == "fssai_licence_number"
        )
        self.assertEqual(
            item["status"],
            "SUSPECTED_TEST_OR_PLACEHOLDER_VALUE",
        )

    def test_missing_field_not_a_violation(self):
        result = self.assess()
        item = next(
            item for item in result["findings"]
            if item["field"] == "net_quantity"
        )
        self.assertEqual(item["status"], "NOT_DETECTED")
        self.assertEqual(item["severity"], "INFORMATION_GAP")
        self.assertIsNone(result["compliance_verdict"])

    def test_gazette_classification(self):
        document = {
            "extracted_text": (
                "THE GAZETTE OF INDIA EXTRAORDINARY\n"
                "MINISTRY OF HEALTH AND FAMILY WELFARE\n"
            ),
            "label_fields": {"fields": []},
        }
        result = self.assess(document)
        self.assertEqual(
            result["document_type"],
            "POSSIBLE_REGULATORY_NOTIFICATION",
        )
        self.assertIsNotNone(result["source_document_warning"])

    def test_no_compliance_decision(self):
        result = self.assess()
        self.assertFalse(result["assessment_complete"])
        self.assertFalse(result["document_facts_verified"])
        self.assertIsNone(result["compliance_verdict"])

    def test_amendment_candidate_retained(self):
        result = self.assess()
        self.assertEqual(
            result["potentially_relevant_amendments"][0]["amendment_id"],
            "TEST-AMENDMENT",
        )

    def test_authenticated_route(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: object()

        with patch(
            "backend.app.services.regulatory_document_extraction.extract_regulatory_document",
            return_value=sample_document(),
        ), patch(
            "backend.app.services.regulatory_label_screening.screen_product",
            side_effect=fake_regulatory_screen,
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/regulatory/assessment/label-preview",
                    data={
                        "product_type": "bread",
                        "assessment_date": "2026-11-18",
                    },
                    files={
                        "file": (
                            "sample.png",
                            io.BytesIO(
                                bytes.fromhex("89504e470d0a1a0a")
                            ),
                        )
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["compliance_verdict"])

    def test_authentication_rejection(self):
        app = FastAPI()
        app.include_router(router)

        def reject():
            raise HTTPException(status_code=401)

        app.dependency_overrides[get_current_user] = reject

        with TestClient(app) as client:
            response = client.post(
                "/regulatory/assessment/label-preview",
                data={
                    "product_type": "bread",
                    "assessment_date": "2026-11-18",
                },
                files={"file": ("sample.png", b"test")},
            )

        self.assertEqual(response.status_code, 401)

    def test_invalid_category_rejected(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: object()

        with TestClient(app) as client:
            response = client.post(
                "/regulatory/assessment/label-preview",
                data={
                    "product_type": "unknown",
                    "assessment_date": "2026-11-18",
                },
                files={"file": ("sample.png", b"test")},
            )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
'''

api_source = '''
// PHASE_3J_LABEL_SCREENING_API
export type RegulatoryLabelFinding = {
  field: string;
  status: string;
  severity: string;
  value: string | null;
  evidence_text: string | null;
  line_number: number | null;
  message: string;
};

export type RegulatoryLabelAssessment = {
  product_type: RegulatoryProductType;
  assessment_date: string;
  document_type: string;
  document_type_verified: false;
  text_extraction_status: string;
  compliance_verdict: null;
  document_facts_verified: false;
  legal_review_status: string;
  detected_field_count: number;
  findings: RegulatoryLabelFinding[];
  candidate_amendment_count: number;
  potentially_relevant_amendments: {
    amendment_id: string;
    date_status: string;
    affected_provisions: string[];
    compliance_verdict: null;
  }[];
  source_document_warning: string | null;
  notice: string;
};

export function regulatoryLabelAssessment(
  file: File,
  productType: RegulatoryProductType,
  assessmentDate: string
) {
  const data = new FormData();
  data.append("file", file);
  data.append("product_type", productType);
  data.append("assessment_date", assessmentDate);
  return request<RegulatoryLabelAssessment>(
    "/regulatory/assessment/label-preview",
    { method: "POST", body: data }
  );
}

'''

panel_import = '''
  regulatoryLabelAssessment,
  type RegulatoryLabelAssessment,
'''

panel_state = '''
  const [labelAssessment, setLabelAssessment] =
    useState<RegulatoryLabelAssessment | null>(null);
  const [labelAssessmentBusy, setLabelAssessmentBusy] = useState(false);
  const [labelAssessmentError, setLabelAssessmentError] = useState("");

  async function runLabelScreening() {
    if (!documentFile) return;
    setLabelAssessmentBusy(true);
    setLabelAssessment(null);
    setLabelAssessmentError("");
    try {
      const result = await regulatoryLabelAssessment(
        documentFile, productType, date
      );
      setLabelAssessment(result);
    } catch (error) {
      setLabelAssessmentError(
        error instanceof Error
          ? error.message
          : "Label screening failed."
      );
    } finally {
      setLabelAssessmentBusy(false);
    }
  }
'''

panel_ui = '''
            <div style={{
              marginTop: 20,
              borderTop: "1px solid #e3e9df",
              paddingTop: 18
            }}>
              <button
                type="button"
                className="button button-secondary"
                onClick={runLabelScreening}
                disabled={!documentFile || labelAssessmentBusy}
              >
                {labelAssessmentBusy
                  ? "Screening label evidence..."
                  : "Screen label evidence"}
              </button>

              {labelAssessmentError && (
                <p role="alert" style={{ color: "#a43a38" }}>
                  {labelAssessmentError}
                </p>
              )}

              {labelAssessment && (
                <div style={{ marginTop: 18 }}>
                  <h3>Preliminary regulatory evidence review</h3>
                  <p style={secondary}>
                    Document classification:
                    {" "}{labelAssessment.document_type.replaceAll("_", " ")}
                  </p>

                  {labelAssessment.source_document_warning && (
                    <p role="alert" style={{ color: "#966021" }}>
                      {labelAssessment.source_document_warning}
                    </p>
                  )}

                  <p style={secondary}>
                    Candidate amendments:
                    {" "}{labelAssessment.candidate_amendment_count}.
                    Product applicability is not legally verified.
                  </p>

                  {labelAssessment.findings.map(item => (
                    <div
                      key={item.field}
                      style={{
                        borderTop: "1px solid #e3e9df",
                        padding: "13px 0",
                        overflowWrap: "anywhere"
                      }}
                    >
                      <strong>{item.field.replaceAll("_", " ")}</strong>
                      <p style={{
                        ...secondary,
                        margin: "5px 0"
                      }}>
                        Status: {item.status.replaceAll("_", " ")}
                      </p>
                      {item.value && <p>{item.value}</p>}
                      <p style={secondary}>{item.message}</p>
                      {item.evidence_text && (
                        <p style={secondary}>
                          Source line {item.line_number}:
                          {" "}{item.evidence_text}
                        </p>
                      )}
                    </div>
                  ))}

                  <p style={{
                    ...secondary,
                    fontWeight: 600,
                    marginTop: 16
                  }}>
                    {labelAssessment.notice}
                  </p>
                </div>
              )}
            </div>
'''

try:
    if not all(path.is_file() for path in existing):
        raise RuntimeError("Required application source missing")
    if any(path.exists() for path in created):
        raise RuntimeError("Phase 3J files already exist")

    originals = {
        path: path.read_text(encoding="utf-8-sig")
        for path in existing
    }

    if "PHASE_3H_DOCUMENT_EXTRACTION" not in originals[route]:
        raise RuntimeError("Phase 3H route not installed")
    if "PHASE_3I" in originals[route]:
        raise RuntimeError("Unexpected regulatory route changes")

    updated_route = originals[route] + route_source

    updated_api = replace_once(
        originals[api],
        "export function regulatoryDocumentExtract(file: File) {",
        api_source +
        "export function regulatoryDocumentExtract(file: File) {",
        "Regulatory screening API",
    )

    updated_panel = replace_once(
        originals[panel],
        "  regulatoryDocumentExtract,",
        "  regulatoryDocumentExtract,"
        + chr(10) + panel_import,
        "Regulatory panel imports",
    )

    updated_panel = replace_once(
        updated_panel,
        "  const [documentBusy, setDocumentBusy] = useState(false);",
        "  const [documentBusy, setDocumentBusy] = useState(false);"
        + chr(10) + panel_state,
        "Regulatory screening component state",
    )

    updated_panel = replace_once(
        updated_panel,
        "            {documentResult.label_fields && (",
        panel_ui
        + chr(10)
        + "            {documentResult.label_fields && (",
        "Regulatory screening results UI",
    )

    # Reset stale screening results when a new document is chosen.
    updated_panel = replace_once(
        updated_panel,
        "              setDocumentResult(null);",
        "              setDocumentResult(null);"
        + chr(10) + "              setLabelAssessment(null);",
        "Document selection state reset",
    )

    ast.parse(service_source)
    ast.parse(route_source)
    ast.parse(tests_source)

except Exception as exc:
    log("STATUS: FAILED_BEFORE_CHANGES")
    log("ERROR: " + str(exc))
    save()
    sys.exit(1)

backup.mkdir(parents=True, exist_ok=False)

for path in existing:
    destination = backup / path.relative_to(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)

log("BACKUP: " + str(backup))

try:
    route.write_text(updated_route, encoding="utf-8")
    api.write_text(updated_api, encoding="utf-8")
    panel.write_text(updated_panel, encoding="utf-8")
    service.write_text(service_source, encoding="utf-8")
    tests.write_text(tests_source, encoding="utf-8")

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm unavailable")

    checks = [
        (
            "PYTHON_COMPILE",
            [
                sys.executable, "-m", "py_compile",
                str(route), str(service), str(tests),
            ],
            root,
        ),
        (
            "BACKEND_TESTS",
            [
                sys.executable, "-m", "unittest", "discover",
                "-s", "backend/tests",
                "-p", "test_regulatory_phase3j.py", "-v",
            ],
            root,
        ),
        (
            "FRONTEND_TYPECHECK",
            [npm, "run", "typecheck"],
            root / "frontend",
        ),
        (
            "FRONTEND_BUILD",
            [npm, "run", "build"],
            root / "frontend",
        ),
    ]

    for label, command, directory in checks:
        log("=== " + label + " ===")

        result = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )

        log(label + "_EXIT_CODE: " + str(result.returncode))
        log((result.stdout + chr(10) + result.stderr)[-7000:])

        if result.returncode:
            raise RuntimeError(label + " failed")

    log("STATUS: PASSED")
    log("LABEL_EVIDENCE_SCREENING: IMPLEMENTED")
    log("AMENDMENT_CANDIDATES: CONNECTED")
    log("DOCUMENT_CLASSIFICATION: PRELIMINARY")
    log("LICENCE_PLACEHOLDER_CHECK: ENABLED")
    log("FINAL_COMPLIANCE_VERDICTS: DISABLED")
    log("FOOD_SCAN_MODIFIED: NO")
    log("DATABASE_MODIFIED: NO")
    log("DOCKER_REBUILD_REQUIRED: YES")

except Exception as exc:
    for path in existing:
        shutil.copy2(backup / path.relative_to(root), path)
    for path in created:
        path.unlink(missing_ok=True)

    log("STATUS: FAILED_AND_ROLLED_BACK")
    log("ERROR: " + str(exc))
    log("SOURCE_FILES_RESTORED: YES")
    save()
    sys.exit(1)

save()
log("REPORT: " + str(report))
