from pathlib import Path
from datetime import datetime
import ast
import shutil
import subprocess
import sys

root = Path.cwd()
dockerfile = root / "backend/Dockerfile"
pyproject = root / "pyproject.toml"
route = root / "backend/app/api/routes/regulatory.py"
api = root / "frontend/src/lib/api.ts"
panel = root / "frontend/src/app/RegulatoryCompliancePanel.tsx"
service = root / "backend/app/services/regulatory_document_extraction.py"
test = root / "backend/tests/test_regulatory_phase3h.py"
report = root / "logs/regulatory_phase3h_report.txt"
backup = root / "backups" / (
    "regulatory_phase3h_" +
    datetime.now().strftime("%Y%m%d_%H%M%S_%f")
)

existing = [dockerfile, pyproject, route, api, panel]
created = [service, test]
notes = ["FOODINSIGHTAI PHASE 3H - OCR AND PDF EXTRACTION"]

def log(message):
    message = str(message)
    notes.append(message)
    print(message, flush=True)

def save():
    report.write_text("\n".join(notes), encoding="utf-8")

def once(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected one anchor, found {count}"
        )
    return source.replace(old, new, 1)

service_source = '''"""Non-persistent OCR and PDF text extraction.

Text is untrusted, may be inaccurate and is never a compliance verdict.
"""

from io import BytesIO
import shutil
from backend.app.services.regulatory_document_intake import (
    inspect_document,
)

MAX_TEXT = 15000
MAX_PAGES = 20
MAX_IMAGE_PIXELS = 18000000


def extract_regulatory_document(filename: str, content: bytes) -> dict:
    result = inspect_document(filename, content)
    result["regulatory_facts_verified"] = False
    result["compliance_verdict"] = None
    result["stored"] = False
    result["extracted_text"] = ""
    result["extracted_character_count"] = 0
    result["truncated"] = False

    if result["document_kind"] == "pdf":
        return _extract_pdf(result, content)
    return _extract_image(result, content)


def _extract_pdf(result: dict, content: bytes) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        result["extraction_status"] = "PDF_ENGINE_NOT_INSTALLED"
        result["notice"] = "PDF parser unavailable in this runtime."
        return result

    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            result["extraction_status"] = "ENCRYPTED_PDF"
            return result

        count = len(reader.pages)
        result["page_count"] = count
        if count > MAX_PAGES:
            result["extraction_status"] = "PAGE_LIMIT_EXCEEDED"
            return result

        chunks = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        extracted = "\\n".join(chunks).strip()

        result["extraction_engine"] = "pypdf"
        result["extracted_text"] = extracted[:MAX_TEXT]
        result["extracted_character_count"] = len(extracted)
        result["truncated"] = len(extracted) > MAX_TEXT
        result["extraction_status"] = (
            "TEXT_EXTRACTED" if extracted else "NO_SELECTABLE_TEXT"
        )
        result["notice"] = (
            "Text extracted from PDF. Scanned PDFs may contain no "
            "selectable text. All extracted information is unverified."
        )
    except Exception:
        result["extraction_status"] = "PDF_EXTRACTION_FAILED"
        result["notice"] = (
            "The PDF could not be parsed reliably; no facts verified."
        )
    return result


def _extract_image(result: dict, content: bytes) -> dict:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
        import warnings

        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            if (
                width < 1 or height < 1
                or width * height > MAX_IMAGE_PIXELS
            ):
                result["extraction_status"] = "IMAGE_DIMENSIONS_REJECTED"
                return result
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image.load()
            processed = ImageOps.exif_transpose(image).convert("RGB")
    except Exception:
        result["extraction_status"] = "INVALID_IMAGE"
        result["notice"] = "Image could not be decoded safely."
        return result

    if shutil.which("tesseract") is None:
        result["extraction_status"] = "IMAGE_OCR_UNAVAILABLE"
        result["notice"] = "OCR executable is not installed."
        return result

    try:
        import pytesseract
    except ImportError:
        result["extraction_status"] = "IMAGE_OCR_UNAVAILABLE"
        result["notice"] = "OCR Python integration is not installed."
        return result

    try:
        extracted = pytesseract.image_to_string(
            processed,
            lang="eng",
            config="--psm 3",
            timeout=20,
        ).strip()
    except Exception:
        result["extraction_status"] = "IMAGE_OCR_FAILED"
        result["notice"] = "OCR failed or exceeded its time limit."
        return result

    result["extraction_engine"] = "tesseract-english"
    result["extracted_text"] = extracted[:MAX_TEXT]
    result["extracted_character_count"] = len(extracted)
    result["truncated"] = len(extracted) > MAX_TEXT
    result["extraction_status"] = (
        "TEXT_EXTRACTED" if extracted else "NO_TEXT_DETECTED"
    )
    result["notice"] = (
        "English OCR text is unverified and may contain errors. "
        "Confirm all extracted label details against the packaging."
    )
    return result
'''

route_addition = '''

# PHASE_3H_DOCUMENT_EXTRACTION
@router.post("/documents/extract")
async def regulatory_document_extract(
    user: AuthenticatedUser,
    file: UploadFile = File(...),
):
    from backend.app.services.regulatory_document_extraction import (
        extract_regulatory_document,
    )

    del user
    try:
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Document exceeds the 8 MB upload limit",
            )
        return extract_regulatory_document(
            file.filename or "", content
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc)
        ) from exc
    finally:
        await file.close()
'''

test_source = '''import io
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
        response = self.upload("label.pdf", b"%PDF-1.4\\ninvalid")
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
'''

api_addition = '''
// PHASE_3H_DOCUMENT_EXTRACTION_API
export function regulatoryDocumentExtract(file: File) {
  const payload = new FormData();
  payload.append("file", file);
  return request<RegulatoryDocumentPreview>(
    "/regulatory/documents/extract",
    { method: "POST", body: payload }
  );
}

'''

try:
    if not all(path.is_file() for path in existing):
        raise RuntimeError("Required source file missing")
    if any(path.exists() for path in created):
        raise RuntimeError("Phase 3H files already exist")

    originals = {
        path: path.read_text(encoding="utf-8-sig")
        for path in existing
    }

    if "PHASE_3G_DOCUMENT_INTAKE" not in originals[route]:
        raise RuntimeError("Phase 3G intake endpoint missing")

    updated = {}

    docker_anchor = (
        "RUN addgroup --system app && "
        "adduser --system --ingroup app app"
    )
    docker_install = (
        "RUN apt-get update && apt-get install -y "
        "--no-install-recommends tesseract-ocr "
        "tesseract-ocr-eng && "
        "rm -rf /var/lib/apt/lists/*"
    )
    updated[dockerfile] = once(
        originals[dockerfile],
        docker_anchor,
        docker_install + chr(10) + docker_anchor,
        "Docker OCR dependency",
    )
    if chr(92) + "nRUN" in updated[dockerfile]:
        raise RuntimeError("Literal newline escape in Dockerfile")

    updated[pyproject] = once(
        originals[pyproject],
        '"pillow>=10.4,<12.0"',
        '"pillow>=10.4,<12.0", '
        '"pypdf>=5.0,<7.0", '
        '"pytesseract>=0.3.13,<1.0"',
        "Python extraction dependencies",
    )

    updated[route] = originals[route] + route_addition

    updated[api] = once(
        originals[api],
        "export function regulatoryDocumentPreview(file: File) {",
        api_addition +
        "export function regulatoryDocumentPreview(file: File) {",
        "Document extraction API",
    )

    modified_panel = once(
        originals[panel],
        "  regulatoryDocumentPreview,",
        "  regulatoryDocumentPreview," + chr(10) + "  regulatoryDocumentExtract,",
        "Regulatory panel API import",
    )

    modified_panel = once(
        modified_panel,
        "await regulatoryDocumentPreview(documentFile)",
        "await regulatoryDocumentExtract(documentFile)",
        "Document upload action",
    )

    modified_panel = modified_panel.replace(
        "Image OCR and regulatory conclusions are not yet enabled.",
        "English image OCR is available when installed. "
        "Extracted text is not a regulatory verdict.",
    )

    updated[panel] = modified_panel

    ast.parse(service_source)
    ast.parse(route_addition)
    ast.parse(test_source)

except Exception as exc:
    log("STATUS: FAILED_BEFORE_CHANGES")
    log("ERROR: " + str(exc))
    save()
    sys.exit(1)

backup.mkdir(parents=True, exist_ok=False)
for path in existing:
    target = backup / path.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

log("BACKUP: " + str(backup))

try:
    for path, content in updated.items():
        path.write_text(content, encoding="utf-8")

    service.write_text(service_source, encoding="utf-8")
    test.write_text(test_source, encoding="utf-8")

    checks = [
        (
            "PYTHON_COMPILE",
            [
                sys.executable, "-m", "py_compile",
                str(route), str(service), str(test)
            ],
            root,
        ),
        (
            "BACKEND_TESTS",
            [
                sys.executable, "-m", "unittest", "discover",
                "-s", "backend/tests",
                "-p", "test_regulatory_phase3h.py", "-v"
            ],
            root,
        ),
    ]

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm unavailable")

    checks.extend([
        ("TYPECHECK", [npm, "run", "typecheck"], root / "frontend"),
        ("BUILD", [npm, "run", "build"], root / "frontend"),
    ])

    for name, command, directory in checks:
        result = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        log(name + "_EXIT_CODE: " + str(result.returncode))
        log((result.stdout + "\\n" + result.stderr)[-6500:])
        if result.returncode:
            raise RuntimeError(name + " failed")

    log("STATUS: PASSED")
    log("PDF_ENGINE: PYPROJECT_DEPENDENCY_ADDED")
    log("OCR_ENGINE: DOCKERFILE_AND_PYPROJECT_UPDATED")
    log("NEW_EXTRACTION_API: ADDED")
    log("STANDALONE_FRONTEND: UPDATED")
    log("FOOD_SCAN_MODIFIED: NO")
    log("COMPLIANCE_VERDICTS: DISABLED")
    log("DOCKER_REBUILD_REQUIRED: YES")

except Exception as exc:
    for path in existing:
        shutil.copy2(backup / path.relative_to(root), path)
    for path in created:
        path.unlink(missing_ok=True)
    log("STATUS: FAILED_AND_ROLLED_BACK")
    log("ERROR: " + str(exc))
    log("SOURCE_FILES_RESTORED: YES")
    save()
    sys.exit(1)

save()
log("REPORT: " + str(report))
