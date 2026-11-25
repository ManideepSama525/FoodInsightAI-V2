from pathlib import Path
import json
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = Path.cwd()
ROUTE = ROOT / "backend/app/api/routes/regulatory.py"
SERVICE = ROOT / "backend/app/services/regulatory_registry.py"
TEST = ROOT / "backend/tests/test_regulatory_phase3b.py"
REGISTRY = ROOT / "data/regulatory/fssai/labelling_amendments_consolidated_v1.json"
REPORT = ROOT / "logs/regulatory_phase3b_implementation_report.txt"

MARKER = "# PHASE_3B_AMENDMENT_STATUS_ENDPOINT"
lines = ["FOODINSIGHTAI PHASE 3B IMPLEMENTATION", ""]

def fail(message):
    lines.append("STATUS: FAILED")
    lines.append("ERROR: " + message)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    sys.exit(1)

for path in (ROUTE, REGISTRY):
    if not path.is_file():
        fail("Missing required file: " + str(path))

if SERVICE.exists() or TEST.exists():
    fail("New Phase 3B file already exists. Refusing to overwrite.")

original = ROUTE.read_text(encoding="utf-8-sig")
if MARKER in original:
    fail("Phase 3B endpoint already appears in regulatory route.")

if 'AuthenticatedUser = Annotated[User, Depends(get_current_user)]' not in original:
    fail("Expected authentication convention not found.")

if 'router = APIRouter(prefix="/regulatory"' not in original:
    fail("Expected regulatory router not found.")

try:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
except (ValueError, UnicodeError) as exc:
    fail("Registry cannot be parsed: " + str(exc))

records = registry.get("amendments", [])
if len(records) != 6 or len({r.get("amendment_id") for r in records}) != 6:
    fail("Expected six unique amendment records.")

if registry.get("legal_review_complete") is not False:
    fail("Legal review status unexpectedly changed.")

if registry.get("compliance_rules_enabled") is not False:
    fail("Compliance rule activation unexpectedly changed.")

service_source = r'''"""Read-only, fail-closed FSSAI amendment registry access."""

import json
from datetime import date
from pathlib import Path

from backend.app.services.regulatory_rule_engine import summarize_amendments


REGISTRY_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "regulatory"
    / "fssai"
    / "labelling_amendments_consolidated_v1.json"
)


class RegistryUnavailable(RuntimeError):
    pass


def load_amendment_registry():
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RegistryUnavailable("Registry unavailable or invalid") from exc

    if not isinstance(data, dict):
        raise RegistryUnavailable("Registry must be an object")

    records = data.get("amendments")
    if not isinstance(records, list) or len(records) != 6:
        raise RegistryUnavailable("Unexpected amendment record count")

    ids = [item.get("amendment_id") for item in records if isinstance(item, dict)]
    if len(ids) != 6 or len(set(ids)) != 6:
        raise RegistryUnavailable("Duplicate or invalid amendment identifiers")

    if data.get("legal_review_complete") is not False:
        raise RegistryUnavailable("Unexpected legal review state")
    if data.get("compliance_rules_enabled") is not False:
        raise RegistryUnavailable("Unexpected rule activation state")

    if any(item.get("compliance_rules_enabled") is not False for item in records):
        raise RegistryUnavailable("Unapproved rule activation in source registry")

    return data


def amendment_status_on(assessment_date: date):
    data = load_amendment_registry()
    items = summarize_amendments(data, assessment_date.isoformat())

    return {
        "authority": "FSSAI",
        "jurisdiction": "India",
        "regulation_family": "Labelling and Display",
        "assessment_date": assessment_date.isoformat(),
        "amendment_count": len(items),
        "legal_review_complete": False,
        "compliance_rules_enabled": False,
        "product_compliance_assessed": False,
        "compliance_verdict": None,
        "notice": (
            "Informational amendment timeline only. "
            "Effective-date status does not establish legal compliance. "
            "Subsequent directions and clause-level review remain pending."
        ),
        "amendments": items,
    }
'''

route_addition = r'''

# PHASE_3B_AMENDMENT_STATUS_ENDPOINT
@router.get("/amendments/status")
def amendment_status(
    user: AuthenticatedUser,
    as_of: __import__("datetime").date | None = Query(default=None),
):
    """Authenticated, read-only amendment timeline; never a compliance verdict."""
    from datetime import date

    from backend.app.services.regulatory_registry import (
        RegistryUnavailable,
        amendment_status_on,
    )

    del user
    try:
        return amendment_status_on(as_of or date.today())
    except RegistryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory amendment registry is unavailable.",
        ) from exc
'''

# Prefer an ordinary module import for the date type.
route_addition = route_addition.replace(
    'as_of: __import__("datetime").date | None',
    "as_of: date | None",
)

if "from datetime import date\n" not in original:
    updated = "from datetime import date\n" + original
else:
    updated = original

updated += route_addition

test_source = r'''import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import regulatory
from backend.app.core.auth import get_current_user
from backend.app.services import regulatory_registry as registry_service


class RegulatoryPhase3BTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(regulatory.router)

    def test_endpoint_requires_authentication(self):
        from fastapi import HTTPException

        def reject_authentication():
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
            )

        self.app.dependency_overrides[get_current_user] = (
            reject_authentication
        )

        with TestClient(self.app) as client:
            response = client.get(
                "/regulatory/amendments/status",
                params={"as_of": "2026-11-18"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"],
            "Authentication required",
        )

    def test_authenticated_request(self):
        self.app.dependency_overrides[get_current_user] = lambda: object()
        with TestClient(self.app) as client:
            response = client.get(
                "/regulatory/amendments/status",
                params={"as_of": "2026-11-18"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["amendment_count"], 6)
        self.assertIsNone(data["compliance_verdict"])
        self.assertFalse(data["product_compliance_assessed"])

    def test_future_amendments(self):
        result = registry_service.amendment_status_on(date(2026, 11, 18))
        statuses = [item["status"] for item in result["amendments"]]
        self.assertEqual(statuses.count("FUTURE_REQUIREMENT"), 2)
        self.assertEqual(statuses.count("EFFECTIVE_DATE_UNRESOLVED"), 2)
        self.assertEqual(statuses.count("PENDING_LEGAL_REVIEW"), 2)

    def test_invalid_date_rejected(self):
        self.app.dependency_overrides[get_current_user] = lambda: object()
        with TestClient(self.app) as client:
            response = client.get(
                "/regulatory/amendments/status",
                params={"as_of": "not-a-date"},
            )
        self.assertEqual(response.status_code, 422)

    def test_missing_registry_fails_closed(self):
        self.app.dependency_overrides[get_current_user] = lambda: object()
        with TemporaryDirectory() as temp:
            missing = Path(temp) / "missing.json"
            with patch.object(registry_service, "REGISTRY_PATH", missing):
                with TestClient(self.app) as client:
                    response = client.get("/regulatory/amendments/status")
        self.assertEqual(response.status_code, 503)

    def test_no_database_dependency_on_new_route(self):
        from backend.app.db.session import get_db

        def reject_database_access():
            raise AssertionError(
                "Read-only amendment endpoint accessed database"
            )

        self.app.dependency_overrides[get_current_user] = (
            lambda: object()
        )
        self.app.dependency_overrides[get_db] = (
            reject_database_access
        )

        with TestClient(self.app) as client:
            response = client.get(
                "/regulatory/amendments/status",
                params={"as_of": "2026-11-18"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["amendment_count"], 6
        )
        self.assertIsNone(
            response.json()["compliance_verdict"]
        )



if __name__ == "__main__":
    unittest.main()
'''

import ast

for label, source in (
    ("service", service_source),
    ("route", updated),
    ("test", test_source),
):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(label + " syntax invalid: " + str(exc))

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = ROUTE.with_name("regulatory_phase3b_backup_" + timestamp + ".py")

try:
    shutil.copy2(ROUTE, backup)
    SERVICE.write_text(service_source, encoding="utf-8")
    TEST.write_text(test_source, encoding="utf-8")
    ROUTE.write_text(updated, encoding="utf-8")

    compile_result = subprocess.run(
        [
            sys.executable, "-m", "py_compile",
            str(ROUTE), str(SERVICE), str(TEST),
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    if compile_result.returncode:
        raise RuntimeError(compile_result.stderr)

    test_result = subprocess.run(
        [
            sys.executable, "-m", "unittest",
            "discover", "-s", "backend/tests",
            "-p", "test_regulatory_phase3b.py", "-v",
        ],
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )

    lines.append("BACKUP: " + str(backup))
    lines.append("COMPILATION: PASSED")
    lines.append("PHASE 3B TEST OUTPUT:")
    lines.append(test_result.stdout)
    lines.append(test_result.stderr)
    lines.append("TEST_EXIT_CODE: " + str(test_result.returncode))

    if test_result.returncode:
        raise RuntimeError("Phase 3B tests failed")

    lines.append("STATUS: PASSED")
    lines.append("AUTHENTICATED_READ_ONLY_ENDPOINT: ADDED")
    lines.append("PRODUCT_COMPLIANCE_VERDICTS: DISABLED")
    lines.append("DATABASE_MODIFIED: NO")

except Exception as exc:
    shutil.copy2(backup, ROUTE)
    if SERVICE.exists():
        SERVICE.unlink()
    if TEST.exists():
        TEST.unlink()

    lines.append("STATUS: FAILED_AND_ROLLED_BACK")
    lines.append("ERROR: " + str(exc))
    lines.append("ORIGINAL_ROUTE_RESTORED: YES")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    sys.exit(1)

REPORT.write_text("\n".join(lines), encoding="utf-8")
print("PHASE 3B: PASSED")
print("REPORT:", REPORT)
print("BACKUP:", backup)
