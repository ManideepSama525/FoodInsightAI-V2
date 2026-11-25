import json
import unittest
from pathlib import Path

from backend.app.services.regulatory_bread_draft_calculator import (
    compare_draft_bread,
)

PATH = Path(
    "data/regulatory/fssai/"
    "bread_draft_requirements_pending_review_v1.json"
)

class Phase3L9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(PATH.read_text(encoding="utf-8"))

    def check(self, category, value):
        return compare_draft_bread(self.registry, category, value)

    def test_exact_whole_wheat_boundary(self):
        self.assertEqual(
            self.check("whole_wheat_bread", "75")[
                "numerical_screening_status"
            ],
            "AT_OR_ABOVE_DRAFT_THRESHOLD",
        )

    def test_below_whole_wheat_boundary(self):
        self.assertEqual(
            self.check("whole_wheat_bread", "74.999")[
                "numerical_screening_status"
            ],
            "BELOW_DRAFT_THRESHOLD",
        )

    def test_brown_bread_boundary(self):
        self.assertEqual(
            self.check("brown_bread", 50)["numerical_screening_status"],
            "AT_OR_ABOVE_DRAFT_THRESHOLD",
        )

    def test_wheat_bread_boundary(self):
        self.assertEqual(
            self.check("wheat_bread", 49.9)["numerical_screening_status"],
            "BELOW_DRAFT_THRESHOLD",
        )

    def test_honey_draft(self):
        self.assertEqual(
            self.check("honey_bread", 5)["numerical_screening_status"],
            "AT_OR_ABOVE_DRAFT_THRESHOLD",
        )

    def test_all_eleven_categories(self):
        self.assertEqual(len(self.registry["requirements"]), 11)
        for item in self.registry["requirements"]:
            result = self.check(item["product_category"], 80)
            self.assertIsNone(result["compliance_verdict"])
            self.assertFalse(result["rule_executed"])
            self.assertFalse(result["product_facts_verified"])

    def test_missing_measurement(self):
        self.assertEqual(
            self.check("milk_bread", None)["numerical_screening_status"],
            "INSUFFICIENT_DATA",
        )

    def test_invalid_measurements(self):
        for value in (True, -1, 101, "NaN", "Infinity", "abc"):
            self.assertEqual(
                self.check("cheese_bread", value)[
                    "numerical_screening_status"
                ],
                "INSUFFICIENT_DATA",
            )

    def test_multigrain_transition_is_not_assumed(self):
        self.assertEqual(
            self.check("multigrain_bread", 25)[
                "numerical_screening_status"
            ],
            "TRANSITIONAL_PERIOD_REVIEW_REQUIRED",
        )

    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):
            self.check("fake_bread", 80)

    def test_draft_registry_cannot_activate(self):
        altered = dict(self.registry)
        altered["compliance_rules_enabled"] = True
        with self.assertRaises(ValueError):
            compare_draft_bread(altered, "honey_bread", 5)

    def test_unapproved_requirement_cannot_activate(self):
        altered = dict(self.registry)
        altered["requirements"] = [
            dict(item) for item in self.registry["requirements"]
        ]
        altered["requirements"][0]["rule_enabled"] = True
        with self.assertRaises(ValueError):
            compare_draft_bread(
                altered, "whole_wheat_bread", 80
            )

    def test_no_legal_verdict_for_low_measurement(self):
        result = self.check("rye_bread", 1)
        self.assertEqual(
            result["numerical_screening_status"],
            "BELOW_DRAFT_THRESHOLD",
        )
        self.assertIsNone(result["compliance_verdict"])

if __name__ == "__main__":
    unittest.main()
