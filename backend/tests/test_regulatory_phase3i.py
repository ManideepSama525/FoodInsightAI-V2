import unittest
from unittest.mock import patch
from backend.app.services.regulatory_label_fields import (
    extract_label_fields,
)
from backend.app.services.regulatory_document_extraction import (
    extract_regulatory_document,
)


class Phase3ITests(unittest.TestCase):
    sample = (
        "INGREDIENTS: Wheat flour, sugar, salt\n"
        "ALLERGENS: Contains wheat and milk\n"
        "NUTRITION INFORMATION\n"
        "Energy 350 kcal\n"
        "Protein 8 g\n"
        "Net Weight: 500 g\n"
        "FSSAI Lic No: 12345678901234\n"
        "MFG: 12/11/2026\n"
        "Best Before: 6 months from packing\n"
    )

    def test_candidate_extraction(self):
        output = extract_label_fields(self.sample)
        self.assertGreaterEqual(output["detected_field_count"], 5)
        self.assertFalse(output["facts_verified"])
        self.assertIsNone(output["compliance_verdict"])

    def test_ingredient_source_evidence(self):
        output = extract_label_fields(self.sample)
        fields = {f["field"]: f for f in output["fields"]}
        self.assertIn("Wheat flour", fields["ingredients"]["value"])
        self.assertEqual(
            fields["ingredients"]["verification_status"],
            "EXTRACTED_UNVERIFIED",
        )
        self.assertGreater(fields["ingredients"]["line_number"], 0)

    def test_licence_requires_exactly_fourteen_digits(self):
        output = extract_label_fields(self.sample)
        fields = {f["field"]: f for f in output["fields"]}
        self.assertEqual(
            fields["fssai_licence_number"]["value"],
            "12345678901234",
        )

    def test_invalid_licence_not_reported(self):
        result = extract_label_fields("FSSAI Lic No: 12345")
        self.assertIn("fssai_licence_number", result["not_detected"])

    def test_no_fields_is_not_noncompliance(self):
        result = extract_label_fields("A photo of a food packet")
        self.assertEqual(result["detected_field_count"], 0)
        self.assertIsNone(result["compliance_verdict"])

    def test_empty_text(self):
        self.assertEqual(
            extract_label_fields("")["detected_field_count"], 0
        )

    def test_does_not_invent_allergens(self):
        result = extract_label_fields("Ingredients: rice and water")
        self.assertIn("allergens", result["not_detected"])

    def test_date_text_not_validated_as_legal_fact(self):
        result = extract_label_fields("MFG: 30/02/2026")
        fields = {f["field"]: f for f in result["fields"]}
        self.assertEqual(
            fields["manufacture_date"]["verification_status"],
            "EXTRACTED_UNVERIFIED",
        )

    def test_document_extraction_integration(self):
        fake = {
            "document_kind": "pdf",
            "extracted_text": self.sample,
            "stored": False,
            "compliance_verdict": None,
        }
        with patch(
            "backend.app.services.regulatory_document_extraction.inspect_document",
            return_value=fake,
        ), patch(
            "backend.app.services.regulatory_document_extraction._extract_pdf",
            return_value=fake,
        ):
            result = extract_regulatory_document("sample.pdf", b"fake")
        self.assertIn("label_fields", result)
        self.assertFalse(result["label_fields"]["facts_verified"])
        self.assertIsNone(result["compliance_verdict"])


if __name__ == "__main__":
    unittest.main()
