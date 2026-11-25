import io
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
