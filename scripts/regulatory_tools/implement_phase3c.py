import ast
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

root = Path.cwd()
route = root / "backend/app/api/routes/regulatory.py"
service = root / "backend/app/services/regulatory_product_screening.py"
test = root / "backend/tests/test_regulatory_phase3c.py"
report = root / "logs/regulatory_phase3c_report.txt"
marker = "# PHASE_3C_PRODUCT_SCREENING"

report.parent.mkdir(parents=True, exist_ok=True)
notes = ["FOODINSIGHTAI PHASE 3C", ""]

def abort(reason):
    notes.extend(["STATUS: FAILED", "ERROR: " + str(reason)])
    report.write_text("\n".join(notes), encoding="utf-8")
    print("\n".join(notes))
    sys.exit(1)

if not route.is_file():
    abort("Existing regulatory route is missing")
if service.exists() or test.exists():
    abort("Phase 3C files already exist")
original = route.read_text(encoding="utf-8-sig")
if marker in original:
    abort("Phase 3C endpoint already exists")
if "PHASE_3B_AMENDMENT_STATUS_ENDPOINT" not in original:
    abort("Phase 3B must be installed first")

service_text = '''"""Conservative product-to-amendment screening.

Category mappings are discovery hints, not legal applicability findings.
No product compliance conclusions are generated.
"""

from datetime import date

from backend.app.services.regulatory_registry import (
    load_amendment_registry,
)
from backend.app.services.regulatory_rule_engine import (
    summarize_amendments,
)

CATEGORY_HINTS = {
    "bread": {"FSSAI-LABEL-AMEND-2", "FSSAI-LABEL-AMEND-3"},
    "coffee_chicory": {"FSSAI-LABEL-AMEND-2", "FSSAI-LABEL-AMEND-4"},
    "milk_product": {"FSSAI-LABEL-AMEND-2", "FSSAI-LABEL-AMEND-6"},
    "edible_oil": {"FSSAI-LABEL-AMEND-1", "FSSAI-LABEL-AMEND-2"},
    "sweetener_product": {
        "FSSAI-LABEL-AMEND-1",
        "FSSAI-LABEL-AMEND-2",
        "FSSAI-LABEL-AMEND-5",
    },
    "other": set(),
}

def screen_product(product_type: str, assessment_date: date):
    registry = load_amendment_registry()
    if product_type not in CATEGORY_HINTS:
        raise ValueError("Unsupported product category")

    timeline = summarize_amendments(
        registry, assessment_date.isoformat()
    )
    by_id = {item["amendment_id"]: item for item in timeline}
    records = {
        item["amendment_id"]: item
        for item in registry["amendments"]
    }

    candidates = []
    for identifier in sorted(CATEGORY_HINTS[product_type]):
        amendment = records[identifier]
        timeline_item = by_id[identifier]
        candidates.append({
            "amendment_id": identifier,
            "date_status": timeline_item["status"],
            "affected_provisions": amendment["affected_provisions"],
            "source_text_sha256": amendment["extracted_text_sha256"],
            "screening_status": "PENDING_LEGAL_REVIEW",
            "product_applicability_verified": False,
            "compliance_verdict": None,
        })

    return {
        "product_type": product_type,
        "assessment_date": assessment_date.isoformat(),
        "jurisdiction": "India",
        "authority": "FSSAI",
        "screening_only": True,
        "assessment_complete": False,
        "product_compliance_assessed": False,
        "compliance_verdict": None,
        "candidate_amendments": candidates,
        "candidate_count": len(candidates),
        "notice": (
            "Category-based discovery only. This is not a complete "
            "list of applicable laws. Product facts, other regulations, "
            "exemptions, legal amendments and directions require review. "
            "No legal compliance finding has been made."
        ),
    }
'''

route_text = '''

# PHASE_3C_PRODUCT_SCREENING
from pydantic import BaseModel, ConfigDict
from typing import Literal


class RegulatoryProductScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_type: Literal[
        "bread",
        "coffee_chicory",
        "milk_product",
        "edible_oil",
        "sweetener_product",
        "other",
    ]
    assessment_date: date


@router.post("/assessment/preview")
def regulatory_product_screening(
    payload: RegulatoryProductScreeningRequest,
    user: AuthenticatedUser,
):
    """Authenticated screening only; no compliance decision."""
    from backend.app.services.regulatory_product_screening import (
        screen_product,
    )
    from backend.app.services.regulatory_registry import RegistryUnavailable

    del user
    try:
        return screen_product(
            payload.product_type,
            payload.assessment_date,
        )
    except RegistryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory registry unavailable",
        ) from exc
'''

test_text = '''import unittest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.routes.regulatory import router
from backend.app.core.auth import get_current_user


class Phase3CTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.app = app

    def request(self, category, when="2026-11-18"):
        self.app.dependency_overrides[get_current_user] = (
            lambda: object()
        )
        with TestClient(self.app) as client:
            return client.post(
                "/regulatory/assessment/preview",
                json={
                    "product_type": category,
                    "assessment_date": when,
                },
            )

    def test_bread_screening(self):
        response = self.request("bread")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["candidate_count"], 2)

    def test_coffee_chicory_screening(self):
        response = self.request("coffee_chicory")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertFalse(data["assessment_complete"])
        self.assertIsNone(data["compliance_verdict"])

    def test_future_milk_amendment(self):
        response = self.request("milk_product")
        self.assertEqual(response.status_code, 200, response.text)
        items = response.json()["candidate_amendments"]
        future = [
            item for item in items
            if item["amendment_id"] == "FSSAI-LABEL-AMEND-6"
        ]
        self.assertEqual(len(future), 1)
        self.assertEqual(
            future[0]["date_status"], "FUTURE_REQUIREMENT"
        )

    def test_unknown_category_rejected(self):
        self.assertEqual(
            self.request("fictional_food").status_code, 422
        )

    def test_invalid_date_rejected(self):
        self.assertEqual(
            self.request("bread", "invalid").status_code, 422
        )

    def test_authentication_rejection(self):
        def reject():
            raise HTTPException(status_code=401)

        self.app.dependency_overrides[get_current_user] = reject
        with TestClient(self.app) as client:
            response = client.post(
                "/regulatory/assessment/preview",
                json={
                    "product_type": "bread",
                    "assessment_date": "2026-11-18",
                },
            )
        self.assertEqual(response.status_code, 401)

    def test_never_generates_compliance_verdicts(self):
        for category in (
            "bread", "coffee_chicory", "milk_product",
            "edible_oil", "sweetener_product", "other",
        ):
            response = self.request(category)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIsNone(data["compliance_verdict"])
            self.assertTrue(data["screening_only"])
            self.assertTrue(all(
                item["compliance_verdict"] is None
                for item in data["candidate_amendments"]
            ))


if __name__ == "__main__":
    unittest.main()
'''

updated = original + route_text
for name, content in (
    ("service", service_text),
    ("route", updated),
    ("tests", test_text),
):
    try:
        ast.parse(content)
    except SyntaxError as exc:
        abort(name + " syntax error: " + str(exc))

backup = route.with_name(
    "regulatory_phase3c_backup_"
    + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    + ".py"
)

try:
    shutil.copy2(route, backup)
    service.write_text(service_text, encoding="utf-8")
    test.write_text(test_text, encoding="utf-8")
    route.write_text(updated, encoding="utf-8")

    command = [
        sys.executable, "-m", "unittest",
        "discover", "-s", "backend/tests",
        "-p", "test_regulatory_phase3c.py", "-v",
    ]
    result = subprocess.run(
        command, cwd=root, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    notes.append("TEST_OUTPUT:")
    notes.append(result.stdout)
    notes.append(result.stderr)
    notes.append("TEST_EXIT_CODE: " + str(result.returncode))
    if result.returncode != 0:
        raise RuntimeError("Phase 3C tests failed")

    notes.extend([
        "STATUS: PASSED",
        "AUTHENTICATED_PRODUCT_SCREENING: ADDED",
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
    report.write_text("\n".join(notes), encoding="utf-8")
    print("PHASE 3C FAILED; SEE REPORT:", report)
    sys.exit(1)

report.write_text("\n".join(notes), encoding="utf-8")
print("PHASE 3C PASSED")
print("REPORT:", report)
