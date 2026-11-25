from pathlib import Path

def replace_once(path, old, new):
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement anchor, found {count}")
    p.write_text(source.replace(old, new), encoding="utf-8")

# Shared regulatory status and freshness policy.
Path("backend/app/services/regulatory_assessment.py").write_text('''from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


FRESHNESS_LIMIT_DAYS = 180
CURRENT_DOCUMENT_STATUSES = {"active"}


def assess_regulatory_evidence(
    provenance: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    provenance = provenance or {}
    status = str(provenance.get("document_status") or "unknown").strip().lower()
    checked_value = provenance.get("last_checked_at")
    current_time = now or datetime.now(timezone.utc)

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    age_days = None
    parse_error = False

    if checked_value:
        try:
            checked_at = datetime.fromisoformat(
                str(checked_value).replace("Z", "+00:00")
            )
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            age_days = max(0, (current_time - checked_at).days)
        except (TypeError, ValueError):
            parse_error = True

    revalidation_due = (
        age_days is None
        or age_days > FRESHNESS_LIMIT_DAYS
        or parse_error
    )

    if status == "active" and not revalidation_due:
        assessment_status = "current_check"
        message = "Document is marked active and was checked within the freshness window."
    elif status == "active":
        assessment_status = "revalidation_due"
        message = "Document is marked active, but its last check is missing, invalid or older than 180 days."
    else:
        assessment_status = "not_current"
        message = f"Document status is '{status}'; it is excluded from current regulatory retrieval."

    return {
        "document_status": status,
        "last_checked_at": checked_value,
        "age_days": age_days,
        "freshness_limit_days": FRESHNESS_LIMIT_DAYS,
        "revalidation_due": revalidation_due,
        "eligible_for_current_retrieval": status in CURRENT_DOCUMENT_STATUSES,
        "assessment_status": assessment_status,
        "message": message,
    }


def is_current_regulatory_evidence(provenance: dict[str, Any] | None) -> bool:
    assessment = assess_regulatory_evidence(provenance)
    return (
        (provenance or {}).get("record_type") == "regulatory_evidence"
        and (provenance or {}).get("official_domain_validated") is True
        and assessment["eligible_for_current_retrieval"]
    )
''', encoding="utf-8")

# Vector indexing: only active, validated regulatory records are indexed.
replace_once(
    "backend/app/services/vector_evidence.py",
    "from backend.app.services.knowledge_graph import knowledge_graph\n",
    "from backend.app.services.knowledge_graph import knowledge_graph\n"
    "from backend.app.services.regulatory_assessment import is_current_regulatory_evidence\n",
)
replace_once(
    "backend/app/services/vector_evidence.py",
    '''        return (
            provenance.get("record_type") == "regulatory_evidence"
            and provenance.get("official_domain_validated") is True
            and all(provenance.get(key) for key in required)
        )
''',
    '''        return (
            provenance.get("record_type") == "regulatory_evidence"
            and provenance.get("official_domain_validated") is True
            and all(provenance.get(key) for key in required)
            and is_current_regulatory_evidence(provenance)
        )
''',
)

# Semantic search: retrieve a larger candidate pool, then filter status and
# attach freshness assessments before selecting top_k.
replace_once(
    "backend/app/services/vector_evidence.py",
    '''            top_k=top_k,
        )

        results = []
''',
    '''            top_k=candidates,
        )

        results = []
''',
)
replace_once(
    "backend/app/services/vector_evidence.py",
    '''            if record["source_type"] == "shared_recipe":
                if provenance.get("owner_scope") != "shared":
                    continue

            results.append({
''',
    '''            if record["source_type"] == "shared_recipe":
                if provenance.get("owner_scope") != "shared":
                    continue

            if record["source_type"] == "regulatory":
                if not _eligible_regulatory_provenance(provenance):
                    continue

            result = {
''',
)
replace_once(
    "backend/app/services/vector_evidence.py",
    '''                "score": float(record["score"]),
            })

        return results
''',
    '''                "score": float(record["score"]),
            }
            if record["source_type"] == "regulatory":
                from backend.app.services.regulatory_assessment import assess_regulatory_evidence
                result["regulatory_assessment"] = assess_regulatory_evidence(provenance)
            results.append(result)

        return results[:top_k]
''',
)

# Helper used by semantic search to enforce the complete regulatory metadata policy.
path = Path("backend/app/services/vector_evidence.py")
source = path.read_text(encoding="utf-8")
anchor = "def ensure_vector_index() -> None:\n"
helper = '''def _eligible_regulatory_provenance(provenance: dict[str, Any]) -> bool:
    required = (
        "authority",
        "jurisdiction",
        "source_url",
        "document_type",
        "document_status",
        "published_at",
        "last_checked_at",
    )
    return (
        provenance.get("record_type") == "regulatory_evidence"
        and provenance.get("official_domain_validated") is True
        and all(provenance.get(key) for key in required)
        and is_current_regulatory_evidence(provenance)
    )


'''
if source.count(anchor) != 1:
    raise RuntimeError("Could not locate vector helper insertion point.")
path.write_text(source.replace(anchor, helper + anchor), encoding="utf-8")

# Hybrid retrieval: reject non-current regulatory records and attach freshness.
replace_once(
    "backend/app/services/hybrid_retrieval.py",
    "from backend.app.services.knowledge_graph import knowledge_graph\n",
    "from backend.app.services.knowledge_graph import knowledge_graph\n"
    "from backend.app.services.regulatory_assessment import (\n"
    "    assess_regulatory_evidence,\n"
    "    is_current_regulatory_evidence,\n"
    ")\n",
)
replace_once(
    "backend/app/services/hybrid_retrieval.py",
    '''        if (
            provenance.get("record_type") != "regulatory_evidence"
            or provenance.get("official_domain_validated") is not True
            or not all(provenance.get(key) for key in required)
        ):
            return

    key = (source_type, source_id)
''',
    '''        if (
            provenance.get("record_type") != "regulatory_evidence"
            or provenance.get("official_domain_validated") is not True
            or not all(provenance.get(key) for key in required)
            or not is_current_regulatory_evidence(provenance)
        ):
            return

        item["regulatory_assessment"] = assess_regulatory_evidence(provenance)

    key = (source_type, source_id)
''',
)
replace_once(
    "backend/app/services/hybrid_retrieval.py",
    '''        "similarity_score": None,
    })
''',
    '''        "similarity_score": None,
        "regulatory_assessment": item.get("regulatory_assessment"),
    })
''',
)

# Regulatory keyword search: current active documents only, with freshness metadata.
replace_once(
    "backend/app/api/routes/regulatory.py",
    "from backend.app.services.regulatory_evidence import (\\n",
    "from backend.app.services.regulatory_assessment import assess_regulatory_evidence\\n"
    "from backend.app.services.regulatory_evidence import (\\n",
)
replace_once(
    "backend/app/api/routes/regulatory.py",
    '''            EvidenceDocument.source_type == "regulatory",
            EvidenceDocument.status == "indexed",
            or_(*conditions),
''',
    '''            EvidenceDocument.source_type == "regulatory",
            EvidenceDocument.status == "indexed",
            EvidenceDocument.provenance["document_status"].as_string() == "active",
            or_(*conditions),
''',
)
replace_once(
    "backend/app/api/routes/regulatory.py",
    '''            "provenance": provenance,
            "content_hash": document.content_hash,
''',
    '''            "provenance": provenance,
            "regulatory_assessment": assess_regulatory_evidence(provenance),
            "content_hash": document.content_hash,
''',
)

# RAG answer: explicitly warn when retrieved active evidence needs revalidation.
replace_once(
    "backend/app/api/routes/rag.py",
    '''    for index, item in enumerate(evidence, start=1):
        lines.append(
''',
    '''    revalidation_due = sum(
        bool((item.get("regulatory_assessment") or {}).get("revalidation_due"))
        for item in evidence
        if item.get("source_type") == "regulatory"
    )
    if revalidation_due:
        lines.append(
            f"Regulatory freshness warning: {revalidation_due} active regulatory "
            "record(s) are older than the 180-day check window or have an invalid "
            "check timestamp. Revalidate the official source before relying on them."
        )

    for index, item in enumerate(evidence, start=1):
        lines.append(
''',
)
replace_once(
    "backend/app/api/routes/rag.py",
    '''            "provenance_assessment": item.get("provenance_assessment"),
        }
''',
    '''            "provenance_assessment": item.get("provenance_assessment"),
            "regulatory_assessment": item.get("regulatory_assessment"),
        }
''',
)

# Search route response and RAG metadata use the same helper; add unit tests.
Path("backend/tests/test_regulatory_assessment.py").write_text('''from datetime import datetime, timedelta, timezone

from backend.app.services.regulatory_assessment import (
    assess_regulatory_evidence,
    is_current_regulatory_evidence,
)


NOW = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)


def provenance(status="active", checked_at="2026-11-01T00:00:00+00:00"):
    return {
        "record_type": "regulatory_evidence",
        "official_domain_validated": True,
        "authority": "Food Safety Authority",
        "jurisdiction": "India",
        "source_url": "https://www.fssai.gov.in/example",
        "document_type": "guidance",
        "document_status": status,
        "published_at": "2026-01-01T00:00:00+00:00",
        "last_checked_at": checked_at,
    }


def test_recent_active_document_is_current():
    result = assess_regulatory_evidence(provenance(), now=NOW)
    assert result["assessment_status"] == "current_check"
    assert result["eligible_for_current_retrieval"] is True
    assert result["revalidation_due"] is False
    assert is_current_regulatory_evidence(provenance())


def test_old_active_document_is_retrievable_but_requires_revalidation():
    old = (NOW - timedelta(days=181)).isoformat()
    data = provenance(checked_at=old)
    result = assess_regulatory_evidence(data, now=NOW)
    assert result["assessment_status"] == "revalidation_due"
    assert result["eligible_for_current_retrieval"] is True
    assert result["revalidation_due"] is True
    assert is_current_regulatory_evidence(data)


def test_missing_or_invalid_check_timestamp_requires_revalidation():
    for value in (None, "not-a-date"):
        data = provenance(checked_at=value)
        result = assess_regulatory_evidence(data, now=NOW)
        assert result["revalidation_due"] is True
        assert result["assessment_status"] == "revalidation_due"


def test_non_active_statuses_are_excluded_from_current_retrieval():
    for status in ("amended", "withdrawn", "superseded", "under_review"):
        data = provenance(status=status)
        result = assess_regulatory_evidence(data, now=NOW)
        assert result["eligible_for_current_retrieval"] is False
        assert result["assessment_status"] == "not_current"
        assert not is_current_regulatory_evidence(data)


def test_unvalidated_record_is_not_current():
    data = provenance()
    data["official_domain_validated"] = False
    assert not is_current_regulatory_evidence(data)
''', encoding="utf-8")

print("Phase 8.4 status and freshness controls patched.")
