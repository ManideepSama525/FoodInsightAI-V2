import unittest
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
