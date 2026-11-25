from pathlib import Path
from datetime import datetime
import ast
import shutil
import subprocess
import sys

root = Path.cwd()
extractor = root / "backend/app/services/regulatory_document_extraction.py"
fields_service = root / "backend/app/services/regulatory_label_fields.py"
tests = root / "backend/tests/test_regulatory_phase3i.py"
api = root / "frontend/src/lib/api.ts"
panel = root / "frontend/src/app/RegulatoryCompliancePanel.tsx"
report = root / "logs/regulatory_phase3i_report.txt"
backup = root / "backups" / (
    "regulatory_phase3i_" +
    datetime.now().strftime("%Y%m%d_%H%M%S_%f")
)

original_files = [extractor, api, panel]
new_files = [fields_service, tests]
notes = ["FOODINSIGHTAI PHASE 3I - STRUCTURED LABEL EXTRACTION"]

def log(message):
    value = str(message)
    notes.append(value)
    print(value, flush=True)

def save():
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(notes), encoding="utf-8")

def replace_once(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            label + ": expected one anchor, found " + str(count)
        )
    return source.replace(old, new, 1)

fields_source = '"""Conservative deterministic extraction of food-label declarations.\n\nFields are text candidates, never verified regulatory facts.\nNo LLM, external requests, persistence, or compliance conclusions.\n"""\n\nimport re\n\nMAX_INPUT = 15000\nMAX_FIELD_VALUE = 1200\nFIELD_NAMES = (\n    "ingredients",\n    "allergens",\n    "nutrition_section",\n    "fssai_licence_number",\n    "net_quantity",\n    "manufacture_date",\n    "best_before",\n    "expiry_date",\n)\n\nHEADING_RE = re.compile(\n    r"^(?:ingredients?|ingredient list|allergens?|allergy advice|"\n    r"contains|nutrition(?:al)? (?:information|facts)|"\n    r"fssai|net (?:wt|weight|quantity|qty)|net contents?|"\n    r"mfg|manufactur(?:ing|ed)|packed on|best before|"\n    r"expiry|exp(?:iry)? date)\\b",\n    re.IGNORECASE,\n)\n\nPATTERNS = (\n    (\n        "ingredients",\n        re.compile(\n            r"^(?:ingredients?|ingredient list)\\s*[:\\-]\\s*(.+)$",\n            re.IGNORECASE,\n        ),\n    ),\n    (\n        "allergens",\n        re.compile(\n            r"^(?:allergens?|allergy advice|contains)\\s*[:\\-]\\s*(.+)$",\n            re.IGNORECASE,\n        ),\n    ),\n    (\n        "nutrition_section",\n        re.compile(\n            r"^(?:nutrition(?:al)? (?:information|facts)|"\n            r"nutrition facts)\\s*[:\\-]?\\s*(.*)$",\n            re.IGNORECASE,\n        ),\n    ),\n    (\n        "net_quantity",\n        re.compile(\n            r"^(?:net (?:wt|weight|quantity|qty)\\.?|net contents?)"\n            r"\\s*[:\\-]?\\s*(\\d+(?:\\.\\d+)?\\s*"\n            r"(?:kg|g|ml|l|litre|liter|grams))\\b",\n            re.IGNORECASE,\n        ),\n    ),\n    (\n        "manufacture_date",\n        re.compile(\n            r"^(?:mfg(?:\\.?\\s*date)?|manufactur(?:ing|ed)"\n            r"(?:\\s*date)?|packed on)\\s*[:\\-]\\s*(.{3,60})$",\n            re.IGNORECASE,\n        ),\n    ),\n    (\n        "best_before",\n        re.compile(\n            r"^best before\\s*[:\\-]\\s*(.{3,60})$",\n            re.IGNORECASE,\n        ),\n    ),\n    (\n        "expiry_date",\n        re.compile(\n            r"^(?:expiry(?:\\s*date)?|exp\\.?\\s*date)"\n            r"\\s*[:\\-]\\s*(.{3,60})$",\n            re.IGNORECASE,\n        ),\n    ),\n)\n\nLICENCE_PATTERN = re.compile(\n    r"\\b(?:FSSAI(?:\\s+(?:LIC(?:EN[CS]E)?|REGISTRATION))?"\n    r"|LICEN[CS]E\\s+NO\\.?)\\s*(?:NO\\.?)?\\s*[:#.-]?\\s*"\n    r"([0-9][0-9\\s-]{12,22}[0-9])",\n    re.IGNORECASE,\n)\n\n\ndef extract_label_fields(text: str) -> dict:\n    if not isinstance(text, str):\n        raise TypeError("Document text must be a string")\n\n    source = text[:MAX_INPUT]\n    lines = [\n        (number, " ".join(raw.split()))\n        for number, raw in enumerate(source.splitlines(), 1)\n        if raw.strip()\n    ]\n\n    results = []\n    present = set()\n\n    def add(field, value, line, line_number):\n        value = " ".join(value.split()).strip(" :-")\n        if not value or field in present:\n            return\n        present.add(field)\n        results.append({\n            "field": field,\n            "value": value[:MAX_FIELD_VALUE],\n            "evidence_text": line[:MAX_FIELD_VALUE],\n            "line_number": line_number,\n            "verification_status": "EXTRACTED_UNVERIFIED",\n        })\n\n    for index, (line_number, line) in enumerate(lines):\n        licence = LICENCE_PATTERN.search(line)\n        if licence and "fssai_licence_number" not in present:\n            digits = re.sub(r"\\D", "", licence.group(1))\n            if len(digits) == 14:\n                add(\n                    "fssai_licence_number", digits,\n                    line, line_number,\n                )\n\n        for field, pattern in PATTERNS:\n            match = pattern.match(line)\n            if not match:\n                continue\n            value = match.group(1).strip()\n\n            if field == "nutrition_section":\n                continuation = []\n                for _, following in lines[index + 1:index + 9]:\n                    if HEADING_RE.match(following):\n                        break\n                    continuation.append(following)\n                value = " ".join([value, *continuation]).strip()\n                if not value:\n                    continue\n\n            if field == "ingredients" and not value:\n                continue\n\n            if field in ("manufacture_date", "best_before", "expiry_date"):\n                value = value[:60]\n\n            add(field, value, line, line_number)\n\n    return {\n        "extraction_method": "DETERMINISTIC_TEXT_PATTERNS",\n        "source_text_truncated": len(text) > MAX_INPUT,\n        "fields": results,\n        "detected_field_count": len(results),\n        "not_detected": [\n            name for name in FIELD_NAMES if name not in present\n        ],\n        "facts_verified": False,\n        "compliance_verdict": None,\n        "notice": (\n            "Text-pattern matches are unverified candidates. "\n            "OCR errors, nonstandard layouts and missing declarations "\n            "can cause missed or incorrect matches. "\n            "Not detected does not mean legally missing."\n        ),\n    }\n'

tests_source = 'import unittest\nfrom unittest.mock import patch\nfrom backend.app.services.regulatory_label_fields import (\n    extract_label_fields,\n)\nfrom backend.app.services.regulatory_document_extraction import (\n    extract_regulatory_document,\n)\n\n\nclass Phase3ITests(unittest.TestCase):\n    sample = (\n        "INGREDIENTS: Wheat flour, sugar, salt\\n"\n        "ALLERGENS: Contains wheat and milk\\n"\n        "NUTRITION INFORMATION\\n"\n        "Energy 350 kcal\\n"\n        "Protein 8 g\\n"\n        "Net Weight: 500 g\\n"\n        "FSSAI Lic No: 12345678901234\\n"\n        "MFG: 12/11/2026\\n"\n        "Best Before: 6 months from packing\\n"\n    )\n\n    def test_candidate_extraction(self):\n        output = extract_label_fields(self.sample)\n        self.assertGreaterEqual(output["detected_field_count"], 5)\n        self.assertFalse(output["facts_verified"])\n        self.assertIsNone(output["compliance_verdict"])\n\n    def test_ingredient_source_evidence(self):\n        output = extract_label_fields(self.sample)\n        fields = {f["field"]: f for f in output["fields"]}\n        self.assertIn("Wheat flour", fields["ingredients"]["value"])\n        self.assertEqual(\n            fields["ingredients"]["verification_status"],\n            "EXTRACTED_UNVERIFIED",\n        )\n        self.assertGreater(fields["ingredients"]["line_number"], 0)\n\n    def test_licence_requires_exactly_fourteen_digits(self):\n        output = extract_label_fields(self.sample)\n        fields = {f["field"]: f for f in output["fields"]}\n        self.assertEqual(\n            fields["fssai_licence_number"]["value"],\n            "12345678901234",\n        )\n\n    def test_invalid_licence_not_reported(self):\n        result = extract_label_fields("FSSAI Lic No: 12345")\n        self.assertIn("fssai_licence_number", result["not_detected"])\n\n    def test_no_fields_is_not_noncompliance(self):\n        result = extract_label_fields("A photo of a food packet")\n        self.assertEqual(result["detected_field_count"], 0)\n        self.assertIsNone(result["compliance_verdict"])\n\n    def test_empty_text(self):\n        self.assertEqual(\n            extract_label_fields("")["detected_field_count"], 0\n        )\n\n    def test_does_not_invent_allergens(self):\n        result = extract_label_fields("Ingredients: rice and water")\n        self.assertIn("allergens", result["not_detected"])\n\n    def test_date_text_not_validated_as_legal_fact(self):\n        result = extract_label_fields("MFG: 30/02/2026")\n        fields = {f["field"]: f for f in result["fields"]}\n        self.assertEqual(\n            fields["manufacture_date"]["verification_status"],\n            "EXTRACTED_UNVERIFIED",\n        )\n\n    def test_document_extraction_integration(self):\n        fake = {\n            "document_kind": "pdf",\n            "extracted_text": self.sample,\n            "stored": False,\n            "compliance_verdict": None,\n        }\n        with patch(\n            "backend.app.services.regulatory_document_extraction.inspect_document",\n            return_value=fake,\n        ), patch(\n            "backend.app.services.regulatory_document_extraction._extract_pdf",\n            return_value=fake,\n        ):\n            result = extract_regulatory_document("sample.pdf", b"fake")\n        self.assertIn("label_fields", result)\n        self.assertFalse(result["label_fields"]["facts_verified"])\n        self.assertIsNone(result["compliance_verdict"])\n\n\nif __name__ == "__main__":\n    unittest.main()\n'

frontend_type = '''
export type RegulatoryLabelField = {
  field: string;
  value: string;
  evidence_text: string;
  line_number: number;
  verification_status: "EXTRACTED_UNVERIFIED";
};

export type RegulatoryLabelExtraction = {
  extraction_method: string;
  source_text_truncated: boolean;
  fields: RegulatoryLabelField[];
  detected_field_count: number;
  not_detected: string[];
  facts_verified: false;
  compliance_verdict: null;
  notice: string;
};

'''

frontend_ui = '''
            {documentResult.label_fields && (
              <div style={{ marginTop: 20 }}>
                <h3>Detected label declarations</h3>
                <p style={secondary}>
                  {documentResult.label_fields.detected_field_count}
                  {" "}text-based candidate fields detected.
                  None have been independently verified.
                </p>
                {documentResult.label_fields.fields.map(item => (
                  <div key={item.field} style={{
                    borderTop: "1px solid #e3e9df",
                    padding: "12px 0",
                    overflowWrap: "anywhere"
                  }}>
                    <strong>
                      {item.field.replaceAll("_", " ")}
                    </strong>
                    <p style={{ margin: "7px 0" }}>{item.value}</p>
                    <p style={secondary}>
                      Source line {item.line_number}:
                      {" "}{item.evidence_text}
                    </p>
                    <span style={{
                      color: "#946820",
                      fontSize: 12,
                      fontWeight: 600
                    }}>
                      EXTRACTED — NOT VERIFIED
                    </span>
                  </div>
                ))}
                <p style={{ ...secondary, marginTop: 16 }}>
                  Not detected in extracted text:
                  {" "}{documentResult.label_fields.not_detected.length
                    ? documentResult.label_fields.not_detected
                        .map(item => item.replaceAll("_", " ")).join(", ")
                    : "None"}
                </p>
                <p style={secondary}>
                  {documentResult.label_fields.notice}
                </p>
              </div>
            )}
'''

try:
    if not all(path.is_file() for path in original_files):
        raise RuntimeError("Phase 3H application files are missing")
    if any(path.exists() for path in new_files):
        raise RuntimeError("Phase 3I files already exist")

    originals = {
        path: path.read_text(encoding="utf-8-sig")
        for path in original_files
    }

    extraction_anchor = (
        '    if result["document_kind"] == "pdf":'
        + chr(10)
        + '        return _extract_pdf(result, content)'
        + chr(10)
        + '    return _extract_image(result, content)'
    )
    extraction_replacement = (
        '    from backend.app.services.regulatory_label_fields import '
        'extract_label_fields'
        + chr(10)
        + '    if result["document_kind"] == "pdf":'
        + chr(10)
        + '        output = _extract_pdf(result, content)'
        + chr(10)
        + '    else:'
        + chr(10)
        + '        output = _extract_image(result, content)'
        + chr(10)
        + '    output["label_fields"] = extract_label_fields('
        'output.get("extracted_text", ""))'
        + chr(10)
        + '    return output'
    )

    updated_extractor = replace_once(
        originals[extractor],
        extraction_anchor,
        extraction_replacement,
        "OCR structured field integration",
    )

    updated_api = replace_once(
        originals[api],
        "export type RegulatoryDocumentPreview = {",
        frontend_type + "export type RegulatoryDocumentPreview = {",
        "Frontend label types",
    )
    updated_api = replace_once(
        updated_api,
        "  extraction_engine: string | null;",
        "  extraction_engine: string | null;"
        + chr(10)
        + "  label_fields?: RegulatoryLabelExtraction;",
        "Frontend extraction response",
    )

    updated_panel = replace_once(
        originals[panel],
        "            {documentResult.extracted_text && (",
        frontend_ui
        + chr(10)
        + "            {documentResult.extracted_text && (",
        "Structured findings UI",
    )

    ast.parse(fields_source)
    ast.parse(updated_extractor)
    ast.parse(tests_source)

except Exception as exc:
    log("STATUS: FAILED_BEFORE_CHANGES")
    log("ERROR: " + str(exc))
    save()
    sys.exit(1)

backup.mkdir(parents=True, exist_ok=False)
for path in original_files:
    destination = backup / path.relative_to(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)

log("BACKUP: " + str(backup))

try:
    extractor.write_text(updated_extractor, encoding="utf-8")
    api.write_text(updated_api, encoding="utf-8")
    panel.write_text(updated_panel, encoding="utf-8")
    fields_service.write_text(fields_source, encoding="utf-8")
    tests.write_text(tests_source, encoding="utf-8")

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found")

    checks = [
        (
            "PYTHON_COMPILE",
            [
                sys.executable, "-m", "py_compile",
                str(extractor), str(fields_service), str(tests),
            ],
            root,
        ),
        (
            "BACKEND_TESTS",
            [
                sys.executable, "-m", "unittest", "discover",
                "-s", "backend/tests",
                "-p", "test_regulatory_phase3i.py", "-v",
            ],
            root,
        ),
        (
            "FRONTEND_TYPECHECK",
            [npm, "run", "typecheck"],
            root / "frontend",
        ),
        (
            "FRONTEND_BUILD",
            [npm, "run", "build"],
            root / "frontend",
        ),
    ]

    for label, command, directory in checks:
        log("=== " + label + " ===")
        result = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        log(label + "_EXIT_CODE: " + str(result.returncode))
        log((result.stdout + chr(10) + result.stderr)[-7000:])
        if result.returncode != 0:
            raise RuntimeError(label + " failed")

    log("STATUS: PASSED")
    log("STRUCTURED_LABEL_FIELDS: IMPLEMENTED")
    log("SOURCE_TEXT_EVIDENCE: PRESERVED")
    log("FIELD_VERIFICATION: NOT_PERFORMED")
    log("COMPLIANCE_VERDICTS: DISABLED")
    log("FOOD_SCAN_MODIFIED: NO")
    log("DATABASE_MODIFIED: NO")
    log("DOCKER_REBUILD_REQUIRED: YES")

except Exception as exc:
    for path in original_files:
        shutil.copy2(backup / path.relative_to(root), path)
    for path in new_files:
        path.unlink(missing_ok=True)
    log("STATUS: FAILED_AND_ROLLED_BACK")
    log("ERROR: " + str(exc))
    log("SOURCE_FILES_RESTORED: YES")
    save()
    sys.exit(1)

save()
log("REPORT: " + str(report))
