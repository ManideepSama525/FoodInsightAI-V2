from pathlib import Path

path = Path("backend/app/core/config.py")
source = path.read_text(encoding="utf-8")

anchor = '    embedding_cache_dir: Path = Path("storage/model_cache")\n'
addition = '''    embedding_cache_dir: Path = Path("storage/model_cache")
    regulatory_admin_user_ids: list[int] = []

    @field_validator("regulatory_admin_user_ids")
    @classmethod
    def validate_regulatory_admin_ids(cls, values: list[int]) -> list[int]:
        if any(isinstance(value, bool) or value <= 0 for value in values):
            raise ValueError("REGULATORY_ADMIN_USER_IDS must contain positive user IDs")
        if len(values) != len(set(values)):
            raise ValueError("REGULATORY_ADMIN_USER_IDS cannot contain duplicates")
        return values
'''
if source.count(anchor) != 1:
    raise SystemExit("Could not safely locate settings insertion point.")
source = source.replace(anchor, addition)
path.write_text(source, encoding="utf-8")

path = Path("backend/app/api/routes/regulatory.py")
path.write_text('''from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.core.auth import get_current_user
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.evidence_document import EvidenceDocument
from backend.app.models.user import User
from backend.app.schemas.regulatory import (
    RegulatoryEvidenceBatch,
)
from backend.app.services.regulatory_evidence import (
    ingest_regulatory_evidence,
)

router = APIRouter(prefix="/regulatory", tags=["regulatory intelligence"])

AuthenticatedUser = Annotated[User, Depends(get_current_user)]


def require_regulatory_admin(user: AuthenticatedUser) -> User:
    allowed_ids = get_settings().regulatory_admin_user_ids
    if user.id not in allowed_ids:
        raise HTTPException(
            status_code=403,
            detail="Regulatory evidence ingestion is restricted to configured administrators.",
        )
    return user


@router.post("/ingest")
def ingest(
    payload: RegulatoryEvidenceBatch,
    _admin: Annotated[User, Depends(require_regulatory_admin)],
    db: Session = Depends(get_db),
):
    try:
        result = ingest_regulatory_evidence(db, payload.records)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Regulatory evidence ingestion failed.",
        ) from exc


@router.get("/search")
def search(
    user: AuthenticatedUser,
    db: Session = Depends(get_db),
    q: str = Query(min_length=2, max_length=300),
    limit: int = Query(default=10, ge=1, le=50),
):
    del user
    terms = list(dict.fromkeys(
        term.lower()
        for term in q.split()
        if len(term) >= 2
    ))
    if not terms:
        return {"query": q, "count": 0, "results": []}

    conditions = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.extend([
            EvidenceDocument.title.ilike(pattern),
            EvidenceDocument.content.ilike(pattern),
        ])

    documents = db.scalars(
        select(EvidenceDocument)
        .where(
            EvidenceDocument.source_type == "regulatory",
            EvidenceDocument.status == "indexed",
            or_(*conditions),
        )
        .order_by(EvidenceDocument.updated_at.desc())
        .limit(limit)
    ).all()

    results = []
    for document in documents:
        provenance = document.provenance or {}
        if (
            provenance.get("record_type") != "regulatory_evidence"
            or provenance.get("official_domain_validated") is not True
        ):
            continue

        results.append({
            "source_id": document.source_id,
            "title": document.title,
            "content": document.content,
            "provenance": provenance,
            "content_hash": document.content_hash,
        })

    return {"query": q, "count": len(results), "results": results}
''', encoding="utf-8")

path = Path("backend/app/api/router.py")
source = path.read_text(encoding="utf-8")
anchor = "from backend.app.api.routes.rag import router as rag_router\n"
addition = anchor + "from backend.app.api.routes.regulatory import router as regulatory_router\n"
if source.count(anchor) != 1:
    raise SystemExit("Could not safely locate API router import.")
source = source.replace(anchor, addition)

anchor = "api_router.include_router(rag_router)\n"
addition = anchor + "api_router.include_router(regulatory_router)\n"
if source.count(anchor) != 1:
    raise SystemExit("Could not safely locate API router registration.")
source = source.replace(anchor, addition)
path.write_text(source, encoding="utf-8")

print("Created regulatory API and configured administrator allowlist.")
