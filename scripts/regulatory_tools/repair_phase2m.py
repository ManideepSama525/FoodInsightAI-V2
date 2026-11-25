import json
import re
import hashlib
import shutil
import sys
from pathlib import Path
from datetime import date, datetime

root = Path("data/regulatory/fssai")
incoming = root / "amendments" / "incoming"
amendments = root / "amendments"
output = root / "labelling_amendments_consolidated_v1.json"
report = Path("logs/regulatory_phase2m_repaired_report.txt")

sources = [
 ("1", incoming / "Gazette_Notification_Oil_Sweetner_16_09_2021.txt", "2021-09-10", None, "2021-11-17", ["Regulation 7", "Schedule-II"], ["2021", "sweetener"]),
 ("2", incoming / "Gazette_Notification_FSS_Label_12_09_2022.txt", "2022-09-09", None, None, ["Regulation 5", "Regulation 6", "Regulation 8", "Schedule-II"], ["2022", "saturated fat"]),
 ("3", incoming / "Gazette_Notification_Labelling_14_10_2022.txt", "2022-10-11", "2023-05-01", None, ["Schedule-II paragraph 1(3)", "Schedule-II paragraph 2.6"], ["2023", "bread"]),
 ("4", incoming / "coffee chicory_gazette.txt", "2025-08-08", "2026-07-01", None, ["Schedule-II paragraph 2.2"], ["2026", "chicory"]),
 ("5", amendments / "labelling_amendment_2026_03_24.txt", "2026-03-24", "2027-07-01", None, ["Regulation 5", "Regulation 8", "Regulation 10", "Schedule-I", "Schedule-II"], ["2027", "Infant Nutrition"]),
 ("6", amendments / "labelling_amendment_2026_11_06.txt", "2026-11-06", "2028-07-01", None, ["Schedule-I paragraph 3"], ["2028", "milk products"]),
]

baseline = date(2026, 11, 18)
records = []
issues = []

for number, path, published, effective, deadline, affected, terms in sources:
    identifier = "FSSAI-LABEL-AMEND-" + number
    if not path.is_file():
        issues.append(identifier + ": missing file " + str(path))
        continue
    content = path.read_text(encoding="utf-8-sig")
    normalized = " ".join(content.split()).casefold()
    if len(content) < 1000 or "===== PAGE" not in content:
        issues.append(identifier + ": invalid or incomplete extraction")
        continue
    missing = [term for term in terms if term.casefold() not in normalized]
    if missing:
        issues.append(identifier + ": missing expected terms " + repr(missing))
        continue
    current = date.fromisoformat(effective) <= baseline if effective else None
    records.append({
        "amendment_id": identifier,
        "notification_date": published,
        "effective_date": effective,
        "compliance_deadline": deadline,
        "effective_on_baseline_date": current,
        "affected_provisions": affected,
        "extracted_text_file": str(path),
        "extracted_text_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_content_validated": True,
        "effective_date_verification": "pending_clause_review" if effective else "gazette_publication_date_pending",
        "supersession_review": "pending",
        "legal_review": "pending",
        "compliance_rules_enabled": False,
    })

if len(records) != 6 or issues:
    report.write_text("PHASE 2M REPAIR FAILED\n" + "\n".join(issues) + "\nVALID_RECORDS: " + str(len(records)), encoding="utf-8")
    print("VALIDATION FAILED. Existing registry was not changed.")
    print("REPORT:", report)
    sys.exit(1)

registry = {
    "schema_version": "1.0",
    "authority": "FSSAI",
    "jurisdiction": "India",
    "regulation_family": "Labelling and Display",
    "assessment_baseline": baseline.isoformat(),
    "amendment_count": 6,
    "source_reconciliation": "in_progress",
    "legal_review_complete": False,
    "compliance_rules_enabled": False,
    "amendments": records,
}

payload = json.dumps(registry, indent=2, ensure_ascii=False)
assert len(json.loads(payload)["amendments"]) == 6

if output.exists():
    existing = json.loads(output.read_text(encoding="utf-8-sig"))
    if len(existing.get("amendments", [])) == 6:
        raise RuntimeError("Existing registry already has six records; refusing overwrite")
    backup = output.with_name(output.stem + "_invalid_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
    shutil.copy2(output, backup)
    print("BACKUP:", backup)

temporary = output.with_suffix(".json.tmp")
temporary.write_text(payload, encoding="utf-8")
temporary.replace(output)

verified = json.loads(output.read_text(encoding="utf-8"))
assert len(verified["amendments"]) == 6

lines = ["FOODINSIGHTAI PHASE 2M REPAIRED", "AMENDMENTS: 6", "SOURCE_CHECKS: PASSED", ""]
for item in verified["amendments"]:
    lines.append(item["amendment_id"] + " | effective=" + str(item["effective_date"]) + " | baseline_active=" + str(item["effective_on_baseline_date"]))
lines += ["", "LEGAL_REVIEW_COMPLETE: NO", "RULES_ACTIVATED: NO", "DATABASE_MODIFIED: NO", "OUTPUT: " + str(output)]
report.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
