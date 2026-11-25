from pathlib import Path

path = Path("backend/app/services/vector_evidence.py")
lines = path.read_text(encoding="utf-8").splitlines()

# Find the result dictionary in the vector-search loop.
starts = [
    i for i, line in enumerate(lines)
    if line.strip() == "result = {"
]
if len(starts) != 1:
    raise SystemExit(f"Expected one result dictionary, found {len(starts)}")

start = starts[0]
end = None

for i in range(start + 1, min(start + 30, len(lines))):
    if lines[i].strip() == "})":
        end = i
        break

if end is None:
    raise SystemExit("Could not find malformed result dictionary closing line.")

# Replace only the malformed closing line and add the missing append.
lines[end:end + 1] = [
    "            }",
    '            if record["source_type"] == "regulatory":',
    "                from backend.app.services.regulatory_assessment import assess_regulatory_evidence",
    '                result["regulatory_assessment"] = assess_regulatory_evidence(provenance)',
    "            results.append(result)",
]

# Ensure the search function returns only the requested number of results.
for i in range(end + 1, min(end + 15, len(lines))):
    if lines[i].strip() == "return results":
        lines[i] = "        return results[:top_k]"
        break
else:
    raise SystemExit("Could not locate vector search return statement.")

# Insert the regulatory provenance helper if it is not already present.
source = "\n".join(lines) + "\n"
if "def _eligible_regulatory_provenance(" not in source:
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
        raise SystemExit("Could not safely insert regulatory eligibility helper.")
    source = source.replace(anchor, helper + anchor)

path.write_text(source, encoding="utf-8")
print("Repaired vector-search result block.")
