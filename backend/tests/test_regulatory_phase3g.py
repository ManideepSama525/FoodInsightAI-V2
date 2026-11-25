import io
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.routes.regulatory import router
from backend.app.core.auth import get_current_user
from backend.app.services.regulatory_document_intake import (
    inspect_document, MAX_BYTES
)


class Phase3GTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: object()
        self.app = app

    def upload(self, name, payload):
        with TestClient(self.app) as client:
            return client.post(
                "/regulatory/documents/preview",
                files={"file": (name, io.BytesIO(payload))},
            )

    def test_png_intake_without_fake_ocr(self):
        result = self.upload(
            "label.png",
            bytes.fromhex("89504e470d0a1a0a") + b"example",
        )
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertEqual(
            data["extraction_status"], "IMAGE_OCR_NOT_AVAILABLE"
        )
        self.assertFalse(data["stored"])
        self.assertIsNone(data["compliance_verdict"])

    def test_jpeg_intake(self):
        response = self.upload("label.jpg", b"\\xff\\xd8\\xff".decode("unicode_escape").encode("latin1") + b"example")
        self.assertEqual(response.status_code, 200, response.text)

    def test_pdf_invalid_rejected(self):
        self.assertEqual(
            self.upload("label.pdf", b"not a pdf").status_code, 400
        )

    def test_extension_mismatch(self):
        self.assertEqual(
            self.upload("label.pdf", bytes.fromhex("89504e470d0a1a0a")).status_code,
            400,
        )

    def test_excessive_size(self):
        self.assertEqual(
            self.upload("large.png", bytes.fromhex("89504e470d0a1a0a") + b"x" * MAX_BYTES).status_code,
            413,
        )

    def test_empty_file_rejected(self):
        self.assertEqual(
            self.upload("empty.png", b"").status_code, 400
        )

    def test_unsupported_file(self):
        self.assertEqual(
            self.upload("script.exe", b"MZ" + b"x" * 20).status_code,
            400,
        )

    def test_authentication_required(self):
        def reject():
            raise HTTPException(status_code=401)
        self.app.dependency_overrides[get_current_user] = reject
        self.assertEqual(
            self.upload("label.png", bytes.fromhex("89504e470d0a1a0a")).status_code,
            401,
        )

    def test_no_compliance_verdict(self):
        data = inspect_document(
            "label.webp", b"RIFF" + b"0000" + b"WEBP" + b"data"
        )
        self.assertIsNone(data["compliance_verdict"])
        self.assertFalse(data["regulatory_facts_verified"])

    def test_pdf_without_selectable_text_never_approved(self):
        data = inspect_document("sample.pdf", b"%PDF-1.4\\ninvalid")
        self.assertIsNone(data["compliance_verdict"])
        self.assertNotEqual(data["extraction_status"], "TEXT_EXTRACTED")


if __name__ == "__main__":
    unittest.main()
