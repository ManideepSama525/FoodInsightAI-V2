import ast
from pathlib import Path
from backend.app.services.hybrid_retrieval import _merge_candidate

def test_regulatory_search_query_is_outside_term_loop():
    path = Path("backend/app/api/routes/regulatory.py")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "search")
    assignments = [n for n in fn.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "documents" for t in n.targets)]
    assert len(assignments) == 1

def test_hybrid_rejects_missing_regulatory_authority():
    provenance = {
        "record_type": "regulatory_evidence",
        "official_domain_validated": True,
        "jurisdiction": "India",
        "source_url": "https://www.fssai.gov.in/notice",
        "document_type": "guidance",
        "document_status": "active",
        "published_at": "2026-11-01T00:00:00+00:00",
        "last_checked_at": "2026-11-18T00:00:00+00:00",
    }
    candidates = {}
    _merge_candidate(candidates, {
        "source_type": "regulatory",
        "source_id": "MISSING-AUTHORITY",
        "title": "Test regulatory notice",
        "content": "Regulatory evidence",
        "provenance": provenance,
    }, "sql", 1)
    assert candidates == {}
