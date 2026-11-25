import unittest
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
