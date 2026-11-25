"""Phase 3L.8: extract source-backed draft bread requirements.

This script does not enable legal rules or modify application code.
"""
import json
import re
import sys
from pathlib import Path

root = Path.cwd()
input_file = root / "logs/regulatory_phase3l7_bread_evidence.json"
output_file = root / "logs/regulatory_phase3l8_bread_requirements.json"
report_file = root / "logs/regulatory_phase3l8_report.txt"

messages = ["FOODINSIGHTAI PHASE 3L.8 - BREAD REQUIREMENT CANDIDATES"]

def log(value):
    messages.append(str(value))
    print(value, flush=True)

def normalize(value):
    return " ".join(str(value).split()).lower()

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

try:
    evidence = json.loads(input_file.read_text(encoding="utf-8"))

    require(
        evidence["amendment_id"] == "FSSAI-LABEL-AMEND-3",
        "Unexpected amendment"
    )
    require(
        evidence["clause_id"] ==
        "FSSAI-LABEL-AMEND-3-CLAUSE-02",
        "Unexpected clause"
    )
    require(
        evidence["rule_enabled"] is False,
        "Source unexpectedly approved"
    )
    require(
        evidence["legal_review_complete"] is False,
        "Unexpected legal review status"
    )

    pages = {
        page["pdf_page"]: page["extracted_text"]
        for page in evidence["selected_pages"]
    }

    require(set(pages) == {3, 4, 5}, "Missing source pages")

    commencement = normalize(pages[3])
    bread_table = normalize(pages[4])
    continuation = normalize(pages[5])

    require(
        re.search(
            r"come into force on 1st may,\s*2023",
            commencement
        ) is not None,
        "Commencement text not found"
    )
    require(
        "2.6 labelling of various types of bread" in bread_table,
        "Bread provision heading not found"
    )
    require(
        "100g flour basis" in continuation,
        "Flour measurement basis not found"
    )

    # Candidate values must be supported by textual anchors
    # within the same source page, not merely written into JSON.
    definitions = [
        ("whole_wheat_bread", "whole wheat bread",
         "whole wheat flour", 75, 4),
        ("wheat_bread", "wheat bread or brown",
         "whole wheat flour", 50, 4),
        ("brown_bread", "wheat bread or brown",
         "whole wheat flour", 50, 4),
        ("multigrain_bread", "multigrain bread",
         "grains other than wheat", 20, 4),
        ("milk_bread", "milk bread", "milk solids", 6, 4),
        ("honey_bread", "honey bread", "honey", 5, 4),
        ("cheese_bread", "cheese bread", "cheese", 10, 4),
        ("oatmeal_bread", "oatmeal bread", "oats", 15, 4),
        ("rye_bread", "rye bread", "rye flour", 20, 4),
        ("raisin_bread", "raisin bread", "raisins", 10, 4),
        ("bran_bread", "bran bread", "edible bran", 5, 4),
    ]

    requirements = []

    for index, (
        category, label_phrase, ingredient, threshold, page
    ) in enumerate(definitions, 1):

        text = normalize(pages[page])
        label_match = re.search(
            re.escape(label_phrase), text
        )

        require(
            label_match is not None,
            f"Label category not found: {category}"
        )

        # Inspect the category's local table text instead of
        # accepting an unrelated percentage elsewhere on the page.
        nearby = text[
            label_match.start():
            min(len(text), label_match.end() + 210)
        ]

        if category == "multigrain_bread":
            require(
                "20%" in nearby and
                "grains other than wheat" in nearby,
                "Multigrain threshold context mismatch"
            )
        else:
            require(
                re.search(
                    rf"(?<![0-9.]){threshold}\s*%",
                    nearby
                ) is not None,
                f"Threshold context mismatch: {category}"
            )
            require(
                ingredient in nearby,
                f"Ingredient context mismatch: {category}"
            )

        requirements.append({
            "candidate_id": f"BREAD-DRAFT-{index:02d}",
            "product_category": category,
            "specialty_ingredient": ingredient,
            "candidate_minimum_percent": threshold,
            "measurement_basis": "100g_flour",
            "source_amendment_id": evidence["amendment_id"],
            "source_clause_id": evidence["clause_id"],
            "provision_reference": evidence["provision_reference"],
            "source_pdf_sha256": evidence["source_pdf_sha256"],
            "source_pdf_page": page,
            "extraction_evidence_excerpt": nearby[:210],
            "notification_commencement_text_found": True,
            "claimed_commencement_date": "2023-05-01",
            "legal_effective_date_verified": False,
            "supersession_checked": False,
            "exceptions_checked": False,
            "product_applicability_verified": False,
            "formulation_facts_verified": False,
            "rule_enabled": False,
            "compliance_verdict": None,
            "status": "DRAFT_PENDING_LEGAL_REVIEW",
        })

    require(
        "minimum 10%" in continuation and
        "1st year" in continuation and
        "thereafter" in continuation,
        "Multigrain transitional provision not supported"
    )

    result = {
        "schema_version": "1.0",
        "source": "FSSAI_SECOND_AMENDMENT_2022",
        "source_pdf_sha256": evidence["source_pdf_sha256"],
        "provision_reference": "Schedule-II paragraph 2.6",
        "source_pdf_pages": [3, 4, 5],
        "claimed_commencement_date": "2023-05-01",
        "legal_commencement_review_complete": False,
        "measurement_basis": "100g_flour",
        "multigrain_transitional_provision": {
            "first_year_candidate_minimum_percent": 10,
            "subsequent_candidate_minimum_percent": 20,
            "first_year_period_legally_verified": False,
            "source_pdf_page": 5,
            "rule_enabled": False,
        },
        "requirement_count": len(requirements),
        "requirements": requirements,
        "legal_review_complete": False,
        "compliance_rules_enabled": False,
        "rule_execution_performed": False,
        "compliance_verdict": None,
        "notice": (
            "Draft values extracted from one amendment. "
            "Later legal changes, exceptions and product "
            "formulation evidence have not been verified. "
            "These values must not generate legal verdicts."
        ),
    }

    require(len(requirements) == 11, "Incomplete draft table")
    require(
        all(r["rule_enabled"] is False for r in requirements),
        "Rule activation detected"
    )
    require(
        all(r["compliance_verdict"] is None for r in requirements),
        "Unexpected compliance verdict"
    )

    # Fail if stale output exists rather than overwriting
    # previously generated evidence without review.
    require(
        not output_file.exists(),
        "Output already exists; refusing overwrite"
    )

    output_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    log("SOURCE_COMMENCEMENT_TEXT: FOUND")
    log("SOURCE_BREAD_TABLE: FOUND")
    log("SOURCE_FLOUR_BASIS: FOUND")
    log("DRAFT_REQUIREMENTS: 11")
    log("MULTIGRAIN_TRANSITION: RECORDED")
    log("LEGAL_REVIEW_COMPLETE: NO")
    log("COMPLIANCE_RULES_ENABLED: NO")
    log("APPLICATION_FILES_MODIFIED: NO")
    log("DATABASE_MODIFIED: NO")
    log("DOCKER_REBUILD_REQUIRED: NO")
    log("STATUS: PASSED")
    log("OUTPUT: " + str(output_file))
    exit_code = 0

except Exception as exc:
    log("STATUS: FAILED")
    log("ERROR: " + repr(exc))
    exit_code = 1

report_file.write_text(
    "\n".join(messages), encoding="utf-8"
)
log("REPORT: " + str(report_file))
sys.exit(exit_code)
