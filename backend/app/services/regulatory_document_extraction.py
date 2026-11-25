"""Non-persistent OCR and PDF text extraction.

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

    from backend.app.services.regulatory_label_fields import extract_label_fields
    if result["document_kind"] == "pdf":
        output = _extract_pdf(result, content)
    else:
        output = _extract_image(result, content)
    output["label_fields"] = extract_label_fields(output.get("extracted_text", ""))
    return output


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
        extracted = "\n".join(chunks).strip()

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
