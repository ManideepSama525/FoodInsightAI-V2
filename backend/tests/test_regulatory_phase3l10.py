
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.routes.regulatory import (
    router,
    regulatory_bread_draft_preview,
)
from fastapi import HTTPException


class Phase3L10Tests(unittest.TestCase):
    def call(self, category="whole_wheat_bread", value=75, **extra):
        payload = {
            "bread_type": category,
            "ingredient_percent": value,
            "measurement_basis": "100g_flour",
        }
        payload.update(extra)
        return regulatory_bread_draft_preview(
            user=object(),
            payload=payload,
        )

    def test_exact_boundary(self):
        result = self.call()
        self.assertEqual(
            result["numerical_screening_status"],
            "AT_OR_ABOVE_DRAFT_THRESHOLD",
        )

    def test_below_boundary_not_a_legal_violation(self):
        result = self.call(value="74.99")
        self.assertEqual(
            result["numerical_screening_status"],
            "BELOW_DRAFT_THRESHOLD",
        )
        self.assertIsNone(result["compliance_verdict"])

    def test_missing_measurement(self):
        self.assertEqual(
            self.call(value=None)["numerical_screening_status"],
            "INSUFFICIENT_DATA",
        )

    def test_multigrain_transition(self):
        result = self.call("multigrain_bread", 20)
        self.assertEqual(
            result["numerical_screening_status"],
            "TRANSITIONAL_PERIOD_REVIEW_REQUIRED",
        )

    def test_all_categories_retain_no_verdict(self):
        categories = (
            "whole_wheat_bread", "wheat_bread", "brown_bread",
            "multigrain_bread", "milk_bread", "honey_bread",
            "cheese_bread", "oatmeal_bread", "rye_bread",
            "raisin_bread", "bran_bread",
        )
        for category in categories:
            with self.subTest(category=category):
                result = self.call(category, 50)
                self.assertFalse(result["rule_executed"])
                self.assertFalse(result["product_facts_verified"])
                self.assertIsNone(result["compliance_verdict"])

    def test_unknown_category_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.call("invented_bread", 80)
        self.assertEqual(caught.exception.status_code, 422)

    def test_incompatible_basis_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.call(measurement_basis="percent_of_final_product")
        self.assertEqual(caught.exception.status_code, 422)

    def test_client_approval_flag_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.call(compliance_rules_enabled=True)
        self.assertEqual(caught.exception.status_code, 422)

    def test_auth_required_on_http_route(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            response = client.post(
                "/regulatory/assessment/bread-draft-preview",
                json={
                    "bread_type": "whole_wheat_bread",
                    "ingredient_percent": 75,
                    "measurement_basis": "100g_flour",
                },
            )
        self.assertIn(response.status_code, (401, 403))

    def test_invalid_number_remains_insufficient(self):
        self.assertEqual(
            self.call(value="NaN")["numerical_screening_status"],
            "INSUFFICIENT_DATA",
        )


if __name__ == "__main__":
    unittest.main()
