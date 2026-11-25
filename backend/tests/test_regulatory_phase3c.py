import unittest
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
