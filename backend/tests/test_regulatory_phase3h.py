import io
import unittest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.routes.regulatory import router
from backend.app.core.auth import get_current_user
from backend.app.services.regulatory_document_extraction import (
    extract_regulatory_document,
)


class Phase3HTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: object()

    def upload(self, name, content):
        with TestClient(self.app) as client:
            return client.post(
                "/regulatory/documents/extract",
                files={"file": (name, io.BytesIO(content))},
            )

    def test_invalid_image_does_not_produce_facts(self):
        result = extract_regulatory_document(
            "label.png",
            bytes.fromhex("89504e470d0a1a0a") + b"invalid"
        )
        self.assertEqual(result["extraction_status"], "INVALID_IMAGE")
        self.assertIsNone(result["compliance_verdict"])

    def test_valid_png_is_processed_conservatively(self):
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (200, 80), "white").save(
            buffer, format="PNG"
        )
        response = self.upload("label.png", buffer.getvalue())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertIn(data["extraction_status"], (
            "IMAGE_OCR_UNAVAILABLE", "IMAGE_OCR_FAILED",
            "NO_TEXT_DETECTED", "TEXT_EXTRACTED",
        ))
        self.assertFalse(data["stored"])
        self.assertIsNone(data["compliance_verdict"])

    def test_invalid_pdf_not_approved(self):
        response = self.upload("label.pdf", b"%PDF-1.4\ninvalid")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["compliance_verdict"])

    def test_unsupported_extension_rejected(self):
        self.assertEqual(
            self.upload("sample.exe", b"MZtest").status_code, 400
        )

    def test_authentication_required(self):
        def reject():
            raise HTTPException(status_code=401)
        self.app.dependency_overrides[get_current_user] = reject
        result = self.upload(
            "sample.png", bytes.fromhex("89504e470d0a1a0a")
        )
        self.assertEqual(result.status_code, 401)

    def test_content_mismatch_rejected(self):
        result = self.upload(
            "image.pdf", bytes.fromhex("89504e470d0a1a0a")
        )
        self.assertEqual(result.status_code, 400)

    def test_empty_file_rejected(self):
        self.assertEqual(
            self.upload("label.png", b"").status_code, 400
        )

    def test_no_storage_or_regulatory_verdict(self):
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (100, 50), "white").save(
            buffer, format="PNG"
        )
        result = extract_regulatory_document(
            "label.png", buffer.getvalue()
        )
        self.assertFalse(result["stored"])
        self.assertFalse(result["regulatory_facts_verified"])
        self.assertIsNone(result["compliance_verdict"])


if __name__ == "__main__":
    unittest.main()
