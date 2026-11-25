import ast
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

root = Path.cwd()
route = root / "backend/app/api/routes/regulatory.py"
service = root / "backend/app/services/regulatory_bread_screening.py"
test = root / "backend/tests/test_regulatory_phase3d.py"
report = root / "logs/regulatory_phase3d_report.txt"
marker = "# PHASE_3D_BREAD_FACT_SCREENING"

notes = ["FOODINSIGHTAI PHASE 3D - BREAD FACT SCREENING"]

def stop(message):
    notes.extend(["STATUS: FAILED", "ERROR: " + str(message)])
    report.write_text("\n".join(notes), encoding="utf-8")
    print("\n".join(notes))
    sys.exit(1)

if not route.is_file():
    stop("Regulatory API route missing")
if service.exists() or test.exists():
    stop("Phase 3D files already exist")

original = route.read_text(encoding="utf-8-sig")
if marker in original:
    stop("Phase 3D endpoint already present")
if "PHASE_3C_PRODUCT_SCREENING" not in original:
    stop("Phase 3C is required")

service_source = '''"""Draft bread ingredient screening.

Thresholds transcribed from the 2022 FSSAI labelling amendment.
Legal applicability, exceptions and later directions are not verified.
"""

from datetime import date
from backend.app.services.regulatory_registry import load_amendment_registry

DRAFT_THRESHOLDS = {
    "whole_wheat_bread": 75.0,
    "wheat_bread": 50.0,
    "brown_bread": 50.0,
}

def screen_bread_facts(
    bread_type: str,
    whole_wheat_flour_percent,
    assessment_date: date,
):
    registry = load_amendment_registry()
    source = next(
        (
            item for item in registry["amendments"]
            if item["amendment_id"] == "FSSAI-LABEL-AMEND-3"
        ),
        None,
    )
    if source is None:
        raise ValueError("Required amendment evidence missing")

    if bread_type not in DRAFT_THRESHOLDS:
        raise ValueError("Unsupported bread type")

    minimum = DRAFT_THRESHOLDS[bread_type]
    missing = []
    if whole_wheat_flour_percent is None:
        missing.append("whole_wheat_flour_percent_of_total_flour")

    return {
        "product_type": "bread",
        "bread_type": bread_type,
        "assessment_date": assessment_date.isoformat(),
        "jurisdiction": "India",
        "authority": "FSSAI",
        "rule_reference": "Schedule-II paragraph 2.6",
        "amendment_id": "FSSAI-LABEL-AMEND-3",
        "documented_effective_date": source["effective_date"],
        "source_text_sha256": source["extracted_text_sha256"],
        "minimum_whole_wheat_flour_percent_of_total_flour": minimum,
        "supplied_whole_wheat_flour_percent_of_total_flour": (
            whole_wheat_flour_percent
        ),
        "missing_facts": missing,
        "data_sufficiency": (
            "INSUFFICIENT_DATA" if missing else "FACTS_PROVIDED"
        ),
        "legal_review_status": "NEEDS_LEGAL_REVIEW",
        "threshold_assessment_performed": False,
        "product_compliance_assessed": False,
        "compliance_verdict": None,
        "notice": (
            "Draft ingredient screening only. The percentage is a "
            "source-derived candidate threshold, not an approved "
            "compliance rule. Exemptions, supersession, official "
            "directions and product formulation need verification."
        ),
    }
'''

route_addition = '''

# PHASE_3D_BREAD_FACT_SCREENING
from pydantic import Field


class RegulatoryBreadFactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bread_type: Literal[
        "whole_wheat_bread", "wheat_bread", "brown_bread"
    ]
    assessment_date: date
    whole_wheat_flour_percent: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Whole-wheat flour as a percent of total flour",
    )


@router.post("/assessment/bread-facts-preview")
def regulatory_bread_fact_preview(
    payload: RegulatoryBreadFactRequest,
    user: AuthenticatedUser,
):
    from backend.app.services.regulatory_bread_screening import (
        screen_bread_facts,
    )
    from backend.app.services.regulatory_registry import RegistryUnavailable

    del user
    try:
        return screen_bread_facts(
            payload.bread_type,
            payload.whole_wheat_flour_percent,
            payload.assessment_date,
        )
    except RegistryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory registry unavailable",
        ) from exc
'''

tests_source = '''import unittest
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.routes.regulatory import router
from backend.app.core.auth import get_current_user
from backend.app.services.regulatory_bread_screening import screen_bread_facts


class Phase3DTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: object()
        self.app = app

    def post(self, bread_type, percent=None):
        with TestClient(self.app) as client:
            return client.post(
                "/regulatory/assessment/bread-facts-preview",
                json={
                    "bread_type": bread_type,
                    "assessment_date": "2026-11-18",
                    "whole_wheat_flour_percent": percent,
                },
            )

    def test_whole_wheat_threshold_reference(self):
        response = self.post("whole_wheat_bread", 80)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(
            data["minimum_whole_wheat_flour_percent_of_total_flour"], 75
        )
        self.assertIsNone(data["compliance_verdict"])
        self.assertFalse(data["threshold_assessment_performed"])

    def test_brown_bread_threshold_reference(self):
        response = self.post("brown_bread", 55)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["minimum_whole_wheat_flour_percent_of_total_flour"],
            50,
        )

    def test_missing_ingredient_percentage(self):
        response = self.post("wheat_bread")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data_sufficiency"], "INSUFFICIENT_DATA"
        )

    def test_below_threshold_not_called_noncompliant(self):
        response = self.post("whole_wheat_bread", 10)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["compliance_verdict"])
        self.assertEqual(
            response.json()["legal_review_status"], "NEEDS_LEGAL_REVIEW"
        )

    def test_invalid_percentage(self):
        self.assertEqual(
            self.post("whole_wheat_bread", 110).status_code, 422
        )

    def test_negative_percentage(self):
        self.assertEqual(
            self.post("whole_wheat_bread", -5).status_code, 422
        )

    def test_unsupported_product(self):
        self.assertEqual(self.post("pizza", 60).status_code, 422)

    def test_authentication(self):
        def deny():
            raise HTTPException(status_code=401)

        self.app.dependency_overrides[get_current_user] = deny
        self.assertEqual(
            self.post("whole_wheat_bread", 80).status_code, 401
        )

    def test_service_never_returns_approval(self):
        for kind in ("whole_wheat_bread", "wheat_bread", "brown_bread"):
            for value in (None, 0, 50, 75, 100):
                result = screen_bread_facts(
                    kind, value, date(2026, 11, 18)
                )
                self.assertIsNone(result["compliance_verdict"])
                self.assertFalse(result["product_compliance_assessed"])


if __name__ == "__main__":
    unittest.main()
'''

updated = original + route_addition

for label, source in (
    ("route", updated),
    ("service", service_source),
    ("tests", tests_source),
):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        stop(label + " syntax error: " + str(exc))

backup = route.with_name(
    "regulatory_phase3d_backup_"
    + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    + ".py"
)

try:
    shutil.copy2(route, backup)
    service.write_text(service_source, encoding="utf-8")
    test.write_text(tests_source, encoding="utf-8")
    route.write_text(updated, encoding="utf-8")

    compile_result = subprocess.run(
        [
            sys.executable, "-m", "py_compile",
            str(route), str(service), str(test),
        ],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    notes.append("COMPILATION_EXIT_CODE: " + str(
        compile_result.returncode
    ))
    if compile_result.returncode:
        raise RuntimeError(compile_result.stderr)

    result = subprocess.run(
        [
            sys.executable, "-m", "unittest", "discover",
            "-s", "backend/tests",
            "-p", "test_regulatory_phase3d.py", "-v",
        ],
        cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    notes.append("TEST_OUTPUT:")
    notes.append(result.stdout)
    notes.append(result.stderr)
    notes.append("TEST_EXIT_CODE: " + str(result.returncode))
    if result.returncode:
        raise RuntimeError("Phase 3D tests failed")

    notes.extend([
        "STATUS: PASSED",
        "AUTHENTICATED_BREAD_FACT_PREVIEW: ADDED",
        "LEGAL_REVIEW: PENDING",
        "COMPLIANCE_VERDICTS: DISABLED",
        "DATABASE_MODIFIED: NO",
        "BACKUP: " + str(backup),
    ])
except Exception as exc:
    shutil.copy2(backup, route)
    service.unlink(missing_ok=True)
    test.unlink(missing_ok=True)
    notes.extend([
        "STATUS: FAILED_AND_ROLLED_BACK",
        "ERROR: " + str(exc),
        "ORIGINAL_ROUTE_RESTORED: YES",
    ])
    report.write_text("\\n".join(notes).replace("\\\\n", "\\n"), encoding="utf-8")
    print("PHASE 3D FAILED. REPORT:", report)
    sys.exit(1)

report.write_text("\\n".join(notes).replace("\\\\n", "\\n"), encoding="utf-8")
print("PHASE 3D PASSED")
print("REPORT:", report)
