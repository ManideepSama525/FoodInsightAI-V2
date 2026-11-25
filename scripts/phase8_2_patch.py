from pathlib import Path

vector_path = Path("backend/app/services/vector_evidence.py")
hybrid_path = Path("backend/app/services/hybrid_retrieval.py")

vector = vector_path.read_text(encoding="utf-8")
hybrid = hybrid_path.read_text(encoding="utf-8")

old = 'ALLOWED_SOURCE_TYPES = ("food", "nutrient", "shared_recipe")'
new = 'ALLOWED_SOURCE_TYPES = ("food", "nutrient", "shared_recipe", "regulatory")'

if vector.count(old) != 1:
    raise SystemExit("Unexpected vector source allowlist; no changes applied.")
if hybrid.count(old) != 1:
    raise SystemExit("Unexpected hybrid source allowlist; no changes applied.")

vector = vector.replace(old, new)
hybrid = hybrid.replace(old, new)

old_eligible = '''def _eligible(document: EvidenceDocument) -> bool:
    if document.source_type not in ALLOWED_SOURCE_TYPES:
        return False
    if document.source_type == "shared_recipe":
        return document.provenance.get("owner_scope") == "shared"
    return True
'''
new_eligible = '''def _eligible(document: EvidenceDocument) -> bool:
    if document.source_type not in ALLOWED_SOURCE_TYPES:
        return False
    if document.source_type == "shared_recipe":
        return document.provenance.get("owner_scope") == "shared"
    if document.source_type == "regulatory":
        provenance = document.provenance or {}
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
        )
    return True
'''
if vector.count(old_eligible) != 1:
    raise SystemExit("Unexpected vector eligibility function; no changes applied.")
vector = vector.replace(old_eligible, new_eligible)

old_filter = '''        if source_type == "shared_recipe":
            filtered[key] = item
            continue

        if source_type == "food":
'''
new_filter = '''        if source_type in ("shared_recipe", "regulatory"):
            filtered[key] = item
            continue

        if source_type == "food":
'''
if hybrid.count(old_filter) != 1:
    raise SystemExit("Unexpected food-anchor filter; no changes applied.")
hybrid = hybrid.replace(old_filter, new_filter)

old_merge = '''    if source_type not in ALLOWED_SOURCE_TYPES or not source_id:
        return
    if not _eligible_recipe(item):
        return
'''
new_merge = '''    if source_type not in ALLOWED_SOURCE_TYPES or not source_id:
        return
    if not _eligible_recipe(item):
        return
    if source_type == "regulatory":
        provenance = item.get("provenance") or {}
        required = (
            "authority",
            "jurisdiction",
            "source_url",
            "document_type",
            "document_status",
            "published_at",
            "last_checked_at",
        )
        if (
            provenance.get("record_type") != "regulatory_evidence"
            or provenance.get("official_domain_validated") is not True
            or not all(provenance.get(key) for key in required)
        ):
            return
'''
if hybrid.count(old_merge) != 1:
    raise SystemExit("Unexpected candidate merge function; no changes applied.")
hybrid = hybrid.replace(old_merge, new_merge)

vector_path.write_text(vector, encoding="utf-8")
hybrid_path.write_text(hybrid, encoding="utf-8")
print("Updated vector and hybrid retrieval allowlists and regulatory provenance checks.")
