"""Isolated, non-persistent regulatory document intake.

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
        raw = "\n".join(chunks).strip()

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
