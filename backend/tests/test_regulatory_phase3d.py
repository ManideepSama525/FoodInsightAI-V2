import unittest
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
