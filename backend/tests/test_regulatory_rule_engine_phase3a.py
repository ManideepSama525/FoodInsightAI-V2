import importlib.util
import json
import unittest
from pathlib import Path

PATH = Path("backend/app/services/regulatory_rule_engine.py")
spec = importlib.util.spec_from_file_location("regulatory_rule_engine_phase3a", PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class RegulatoryPhase3ATests(unittest.TestCase):
    def setUp(self):
        self.rule = {
            "rule_id": "SYNTHETIC-TEST-ONLY",
            "jurisdiction": "India",
            "effective_date": "2027-07-01",
            "enabled": True,
            "legal_review_status": "verified",
            "supersession_review": "verified",
            "source_url": "https://fssai.gov.in/example.pdf",
            "source_sha256": "a" * 64,
            "applicability": {"product_type": "test_food"},
            "predicate": {
                "field": "test_value",
                "operator": "minimum",
                "value": 10,
                "unit": "g",
            },
        }
        self.facts = {
            "product_type": "test_food",
            "test_value": 12,
            "test_value_unit": "g",
        }

    def evaluate(self, date="2027-07-01"):
        return engine.assess_rule(self.rule, self.facts, date)["status"]

    def test_future_effective_date(self):
        self.assertEqual(self.evaluate("2026-11-18"), "NOT_YET_EFFECTIVE")

    def test_valid_synthetic_rule(self):
        self.assertEqual(self.evaluate(), "COMPLIANT")

    def test_synthetic_violation(self):
        self.facts["test_value"] = 5
        self.assertEqual(self.evaluate(), "NON_COMPLIANT")

    def test_missing_measurement(self):
        del self.facts["test_value"]
        self.assertEqual(self.evaluate(), "INSUFFICIENT_DATA")

    def test_wrong_unit(self):
        self.facts["test_value_unit"] = "mg"
        self.assertEqual(self.evaluate(), "INSUFFICIENT_DATA")

    def test_missing_applicability(self):
        del self.facts["product_type"]
        self.assertEqual(self.evaluate(), "INSUFFICIENT_DATA")

    def test_outside_scope(self):
        self.facts["product_type"] = "other"
        self.assertEqual(self.evaluate(), "NOT_APPLICABLE")

    def test_disabled_rule(self):
        self.rule["enabled"] = False
        self.assertEqual(self.evaluate(), "NEEDS_REVIEW")

    def test_unverified_source(self):
        self.rule["source_url"] = "https://example.com/law.pdf"
        self.assertEqual(self.evaluate(), "NEEDS_REVIEW")

    def test_pending_supersession(self):
        self.rule["supersession_review"] = "pending"
        self.assertEqual(self.evaluate(), "NEEDS_REVIEW")

    def test_expired_version(self):
        self.rule["end_date"] = "2027-08-01"
        self.assertEqual(self.evaluate("2027-08-02"), "NEEDS_REVIEW")

    def test_real_registry_no_verdicts(self):
        registry = json.loads(
            Path(
                "data/regulatory/fssai/labelling_amendments_consolidated_v1.json"
            ).read_text(encoding="utf-8-sig")
        )
        items = engine.summarize_amendments(registry, "2026-11-18")
        self.assertEqual(len(items), 6)
        self.assertTrue(all(x["compliance_verdict"] is None for x in items))
        self.assertEqual(
            sum(x["status"] == "FUTURE_REQUIREMENT" for x in items), 2
        )


if __name__ == "__main__":
    unittest.main()
