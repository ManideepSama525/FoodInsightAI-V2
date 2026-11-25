from pathlib import Path
from datetime import datetime
import ast
import shutil
import subprocess
import sys

root = Path.cwd()
route = root / "backend/app/api/routes/regulatory.py"
service = root / "backend/app/services/regulatory_document_intake.py"
test = root / "backend/tests/test_regulatory_phase3g.py"
api = root / "frontend/src/lib/api.ts"
panel = root / "frontend/src/app/RegulatoryCompliancePanel.tsx"
report = root / "logs/regulatory_phase3g_report.txt"
backup = root / "backups" / (
    "regulatory_phase3g_" +
    datetime.now().strftime("%Y%m%d_%H%M%S_%f")
)

notes = ["FOODINSIGHTAI PHASE 3G - REGULATORY DOCUMENT INTAKE"]

def log(value):
    notes.append(str(value))
    print(value, flush=True)

def save():
    report.write_text("\n".join(notes), encoding="utf-8")

def replace_once(source, before, after, label):
    count = source.count(before)
    if count != 1:
        raise RuntimeError(
            label + ": expected one anchor; found " + str(count)
        )
    return source.replace(before, after, 1)

files = [route, api, panel]
new_files = [service, test]

try:
    if not all(path.is_file() for path in files):
        raise RuntimeError("Required Phase 3E frontend or regulatory route missing")
    if any(path.exists() for path in new_files):
        raise RuntimeError("Phase 3G service/test already present")
    if "PHASE_3D_BREAD_FACT_SCREENING" not in route.read_text(encoding="utf-8-sig"):
        raise RuntimeError("Phase 3D not installed")
    if "PHASE_3E_REGULATORY_API" not in api.read_text(encoding="utf-8-sig"):
        raise RuntimeError("Phase 3E API missing")
except Exception as exc:
    log("STATUS: FAILED")
    log("ERROR: " + str(exc))
    save()
    sys.exit(1)

service_source = '''"""Isolated, non-persistent regulatory document intake.

No OCR, legal inference, compliance verdicts or LLM calls.
Do not treat extracted text as verified product facts.
"""

import hashlib
import io

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 20
MAX_TEXT = 15000


def inspect_document(filename: str, content: bytes) -> dict:
    if not content:
        raise ValueError("Empty document")
    if len(content) > MAX_BYTES:
        raise ValueError("Document exceeds 8 MB limit")

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_types = {
        "pdf": "application/pdf",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    if suffix not in file_types:
        raise ValueError("Only PDF, JPG, PNG and WebP files are supported")

    if content.startswith(b"%PDF-"):
        detected = "application/pdf"
    elif content.startswith(bytes.fromhex("ffd8ff")):
        detected = "image/jpeg"
    elif content.startswith(bytes.fromhex("89504e470d0a1a0a")):
        detected = "image/png"
    elif (
        content.startswith(b"RIFF")
        and content[8:12] == b"WEBP"
    ):
        detected = "image/webp"
    else:
        raise ValueError("File signature is not a supported document")

    if detected != file_types[suffix]:
        raise ValueError("File extension does not match its content")

    result = {
        "filename": filename[-120:],
        "content_type": detected,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "stored": False,
        "document_kind": "pdf" if suffix == "pdf" else "image",
        "extraction_status": "NOT_ATTEMPTED",
        "extraction_engine": None,
        "page_count": None,
        "extracted_text": "",
        "extracted_character_count": 0,
        "truncated": False,
        "regulatory_facts_verified": False,
        "compliance_verdict": None,
        "notice": (
            "Document intake only. Extracted text is unverified. "
            "No regulatory compliance determination was performed."
        ),
    }

    if suffix != "pdf":
        result["extraction_status"] = "IMAGE_OCR_NOT_AVAILABLE"
        result["notice"] = (
            "Image accepted for intake validation only; image OCR "
            "is not yet implemented. No data was extracted or stored."
        )
        return result

    try:
        from pypdf import PdfReader
        engine = "pypdf"
    except ImportError:
        try:
            from PyPDF2 import PdfReader
            engine = "PyPDF2"
        except ImportError:
            result["extraction_status"] = "PDF_ENGINE_NOT_INSTALLED"
            result["notice"] = (
                "PDF validated but extraction library unavailable. "
                "No text was extracted or stored."
            )
            return result

    result["extraction_engine"] = engine

    try:
        reader = PdfReader(io.BytesIO(content))
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
        raw = "\\n".join(chunks).strip()

        result["extracted_character_count"] = len(raw)
        result["extracted_text"] = raw[:MAX_TEXT]
        result["truncated"] = len(raw) > MAX_TEXT
        result["extraction_status"] = (
            "TEXT_EXTRACTED" if raw else "NO_SELECTABLE_TEXT"
        )
    except Exception:
        result["extraction_status"] = "PDF_EXTRACTION_FAILED"
        result["extracted_text"] = ""

    return result
'''

route_addition = '''

# PHASE_3G_DOCUMENT_INTAKE
from fastapi import File, UploadFile
from backend.app.services.regulatory_document_intake import (
    inspect_document, MAX_BYTES
)


@router.post("/documents/preview")
async def regulatory_document_preview(
    user: AuthenticatedUser,
    file: UploadFile = File(...),
):
    """Authenticated, in-memory document inspection only."""
    del user
    try:
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Document exceeds the 8 MB upload limit",
            )
        return inspect_document(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
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
        response = self.upload("label.jpg", b"\\\\xff\\\\xd8\\\\xff".decode("unicode_escape").encode("latin1") + b"example")
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
        data = inspect_document("sample.pdf", b"%PDF-1.4\\\\ninvalid")
        self.assertIsNone(data["compliance_verdict"])
        self.assertNotEqual(data["extraction_status"], "TEXT_EXTRACTED")


if __name__ == "__main__":
    unittest.main()
'''

api_source = '''
// PHASE_3G_DOCUMENT_API
export type RegulatoryDocumentPreview = {
  filename: string;
  content_type: string;
  size_bytes: number;
  document_kind: "pdf" | "image";
  extraction_status: string;
  extraction_engine: string | null;
  page_count: number | null;
  extracted_text: string;
  extracted_character_count: number;
  truncated: boolean;
  stored: false;
  regulatory_facts_verified: false;
  compliance_verdict: null;
  notice: string;
};

export function regulatoryDocumentPreview(file: File) {
  const payload = new FormData();
  payload.append("file", file);
  return request<RegulatoryDocumentPreview>("/regulatory/documents/preview", {
    method: "POST",
    body: payload
  });
}

'''

panel_ui = '''
      <section style={panel}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Upload size={22} color="#497857"/>
          <h2 style={{ margin: 0 }}>Regulatory label document intake</h2>
        </div>
        <p style={secondary}>
          Upload a packaging image or PDF independently of Food Scan.
          PDFs with selectable text can be extracted where a PDF engine
          is available. Image OCR and regulatory conclusions are not yet enabled.
        </p>
        <label style={field}>
          Product label or packaging document (maximum 8 MB)
          <input
            style={control}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp"
            onChange={event => {
              setDocumentFile(event.target.files?.[0] ?? null);
              setDocumentResult(null);
              setDocumentError("");
            }}
          />
        </label>
        <button
          type="button"
          className="button button-primary"
          style={{ marginTop: 16 }}
          disabled={!documentFile || documentBusy}
          onClick={uploadDocument}
        >
          {documentBusy
            ? <LoaderCircle className="spin" size={16}/>
            : <FileSearch size={16}/>}
          {documentBusy ? "Inspecting document..." : "Inspect document"}
        </button>
        {documentError && (
          <p role="alert" style={{ color: "#a43a38", marginTop: 14 }}>
            {documentError}
          </p>
        )}
        {documentResult && (
          <div style={{
            background: "#f6f8f4",
            borderRadius: 12,
            padding: 18,
            marginTop: 18
          }}>
            <strong>Document inspection</strong>
            <p style={secondary}>
              {documentResult.filename} · {documentResult.size_bytes} bytes
            </p>
            <p>
              Extraction: <strong>
                {documentResult.extraction_status.replaceAll("_", " ")}
              </strong>
            </p>
            <p style={secondary}>{documentResult.notice}</p>
            {documentResult.extracted_text && (
              <div>
                <h3>Extracted PDF text (unverified)</h3>
                <textarea
                  aria-label="Extracted document text"
                  readOnly
                  value={documentResult.extracted_text}
                  rows={9}
                  style={{
                    ...control,
                    minHeight: 180,
                    fontFamily: "inherit"
                  }}
                />
                <p style={secondary}>
                  {documentResult.truncated
                    ? "Preview truncated; not all source text is shown."
                    : "Text is not automatically verified or assessed."}
                </p>
              </div>
            )}
          </div>
        )}
      </section>

'''

panel_logic = '''
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [documentResult, setDocumentResult] =
    useState<RegulatoryDocumentPreview | null>(null);
  const [documentBusy, setDocumentBusy] = useState(false);
  const [documentError, setDocumentError] = useState("");

  async function uploadDocument() {
    if (!documentFile) return;
    if (documentFile.size > 8 * 1024 * 1024) {
      setDocumentError("The file exceeds the 8 MB limit.");
      return;
    }
    setDocumentBusy(true);
    setDocumentError("");
    setDocumentResult(null);
    try {
      setDocumentResult(await regulatoryDocumentPreview(documentFile));
    } catch (error) {
      setDocumentError(
        error instanceof Error ? error.message : "Document inspection failed."
      );
    } finally {
      setDocumentBusy(false);
    }
  }

'''

originals = {
    path: path.read_text(encoding="utf-8-sig")
    for path in files
}

try:
    ast.parse(service_source)
    ast.parse(route_addition)
    ast.parse(test_source)

    updated_route = originals[route] + route_addition
    updated_api = replace_once(
        originals[api],
        "export function regulatoryAmendmentStatus(",
        api_source + "export function regulatoryAmendmentStatus(",
        "Regulatory API functions",
    )

    updated_panel = replace_once(
        originals[panel],
        "FileSearch, LoaderCircle, Scale, ShieldAlert",
        "FileSearch, LoaderCircle, Scale, ShieldAlert, Upload",
        "Panel icon imports",
    )
    updated_panel = replace_once(
        updated_panel,
        "  regulatoryBreadPreview,",
        "  regulatoryBreadPreview,\n  regulatoryDocumentPreview,",
        "Document API import",
    )
    updated_panel = replace_once(
        updated_panel,
        "  type RegulatoryBreadResult,",
        "  type RegulatoryBreadResult,\n  type RegulatoryDocumentPreview,",
        "Document type import",
    )
    updated_panel = replace_once(
        updated_panel,
        "  const [busy, setBusy] = useState(false);",
        "  const [busy, setBusy] = useState(false);\n" + panel_logic,
        "Document component state",
    )
    updated_panel = replace_once(
        updated_panel,
        "      {screening && (",
        panel_ui + "      {screening && (",
        "Document upload section",
    )

except Exception as exc:
    log("STATUS: FAILED_BEFORE_CHANGES")
    log("ERROR: " + str(exc))
    save()
    sys.exit(1)

backup.mkdir(parents=True, exist_ok=False)
for path in files:
    shutil.copy2(path, backup / path.name)

log("BACKUP: " + str(backup))

try:
    route.write_text(updated_route, encoding="utf-8")
    api.write_text(updated_api, encoding="utf-8")
    panel.write_text(updated_panel, encoding="utf-8")
    service.write_text(service_source, encoding="utf-8")
    test.write_text(test_source, encoding="utf-8")

    compilation = subprocess.run(
        [
            sys.executable, "-m", "py_compile",
            str(route), str(service), str(test)
        ],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    )
    log("PYTHON_COMPILE_EXIT_CODE: " + str(compilation.returncode))
    if compilation.returncode:
        raise RuntimeError(compilation.stderr)

    checks = [
        (
            "BACKEND_TESTS",
            [
                sys.executable, "-m", "unittest", "discover",
                "-s", "backend/tests",
                "-p", "test_regulatory_phase3g.py", "-v"
            ],
            root,
        )
    ]

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm unavailable")

    checks.extend([
        ("FRONTEND_TYPECHECK", [npm, "run", "typecheck"], root / "frontend"),
        ("FRONTEND_BUILD", [npm, "run", "build"], root / "frontend"),
    ])

    for label, command, workdir in checks:
        log("=== " + label + " ===")
        result = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        log(label + "_EXIT_CODE: " + str(result.returncode))
        log((result.stdout + "\\n" + result.stderr)[-10000:])
        if result.returncode:
            raise RuntimeError(label + " failed")

    log("STATUS: PASSED")
    log("AUTHENTICATED_DOCUMENT_UPLOAD: IMPLEMENTED")
    log("PDF_TEXT_EXTRACTION: OPTIONAL_LIBRARY")
    log("IMAGE_OCR: NOT_YET_IMPLEMENTED")
    log("DOCUMENT_PERSISTENCE: DISABLED")
    log("COMPLIANCE_VERDICTS: DISABLED")
    log("FOOD_SCAN_MODIFIED: NO")
    log("DATABASE_MODIFIED: NO")
    log("DOCKER_REBUILD_REQUIRED: YES")

except Exception as exc:
    for path in files:
        shutil.copy2(backup / path.name, path)
    for path in new_files:
        path.unlink(missing_ok=True)

    log("STATUS: FAILED_AND_ROLLED_BACK")
    log("ERROR: " + str(exc))
    log("APPLICATION_SOURCE_RESTORED: YES")
    save()
    sys.exit(1)

save()
log("REPORT: " + str(report))
