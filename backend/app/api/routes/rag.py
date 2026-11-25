from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.core.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.rag import RagQueryRequest, RagQueryResponse
from backend.app.services.claim_verification import verify_nutrient_claim
from backend.app.services.hybrid_retrieval import retrieve_hybrid_evidence


router = APIRouter(prefix="/rag", tags=["grounded RAG"])

AuthenticatedUser = Annotated[User, Depends(get_current_user)]


def _build_grounded_answer(
    evidence: list[dict[str, Any]],
) -> str:
    if not evidence:
        return (
            "No matching indexed evidence was found. "
            "There is insufficient evidence to answer this query."
        )

    conflicts = sum(
        len(item.get("source_conflicts") or [])
        for item in evidence
    )

    incomparable = sum(
        len(item.get("incomparable_measurements") or [])
        for item in evidence
    )

    assessments = [
        item.get("provenance_assessment") or {}
        for item in evidence
    ]
    partial_count = sum(
        assessment.get("status") == "partial"
        for assessment in assessments
    )
    invalid_count = sum(
        assessment.get("status") == "invalid"
        for assessment in assessments
    )

    lines = [
        f"Retrieved {len(evidence)} relevant evidence records.",
        "The following information is derived from indexed sources:",
    ]

    if invalid_count:
        lines.append(
            f"Warning: {invalid_count} evidence record(s) contain invalid "
            "measurement data. Do not use those measurements as verified values."
        )

    if partial_count:
        lines.append(
            f"Warning: {partial_count} evidence record(s) have incomplete "
            "provenance. Check their attribution before relying on them."
        )

    for index, item in enumerate(evidence, start=1):
        lines.append(
            f"[{index}] {item.get('title') or 'Untitled evidence'}: "
            f"{item.get('content') or 'No content available.'}"
        )

    if conflicts:
        lines.append(
            f"Warning: {conflicts} source conflict(s) were detected."
        )

    if incomparable:
        lines.append(
            f"Warning: {incomparable} measurement comparison(s) "
            "could not be made because their units or bases differ."
        )

    lines.append(
        "This is an evidence summary, not a generated medical or "
        "nutritional recommendation."
    )

    return "\n".join(lines)


@router.post("/query", response_model=RagQueryResponse)
def query_rag(
    request: RagQueryRequest,
    _user: AuthenticatedUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        evidence = retrieve_hybrid_evidence(
            db,
            request.query,
            top_k=request.top_k,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Evidence retrieval is currently unavailable.",
        ) from exc

    verification = None

    if request.claim is not None:
        try:
            verification = verify_nutrient_claim(
                request.claim.model_dump(),
                evidence,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    citations = [
        {
            "citation_id": f"{item['source_type']}:{item['source_id']}",
            "source_type": item["source_type"],
            "source_id": item["source_id"],
            "title": item.get("title"),
            "provenance": item.get("provenance_records") or [
                item.get("provenance") or {}
            ],
            "provenance_assessment": item.get("provenance_assessment"),
        }
        for item in evidence
    ]

    return {
        "query": request.query,
        "answer": _build_grounded_answer(evidence),
        "retrieved_count": len(evidence),
        "evidence": evidence,
        "citations": citations,
        "verification": verification,
    }