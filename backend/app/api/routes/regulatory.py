from datetime import date
from typing import Annotated

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
from backend.app.services.regulatory_assessment import (
    is_current_regulatory_evidence,
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
    ).all()

    required = (
        "authority",
        "jurisdiction",
        "source_url",
        "document_type",
        "document_status",
        "published_at",
        "last_checked_at",
    )

    results = []

    for document in documents:
        provenance = document.provenance or {}

        if (
            not all(provenance.get(key) for key in required)
            or not is_current_regulatory_evidence(provenance)
        ):
            continue

        results.append({
            "source_id": document.source_id,
            "title": document.title,
            "content": document.content,
            "provenance": provenance,
            "content_hash": document.content_hash,
        })

        if len(results) >= limit:
            break

    return {
        "query": q,
        "count": len(results),
        "results": results,
    }

# PHASE_3B_AMENDMENT_STATUS_ENDPOINT
@router.get("/amendments/status")
def amendment_status(
    user: AuthenticatedUser,
    as_of: date | None = Query(default=None),
):
    """Authenticated, read-only amendment timeline; never a compliance verdict."""
    from datetime import date

    from backend.app.services.regulatory_registry import (
        RegistryUnavailable,
        amendment_status_on,
    )

    del user
    try:
        return amendment_status_on(as_of or date.today())
    except RegistryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory amendment registry is unavailable.",
        ) from exc


# PHASE_3C_PRODUCT_SCREENING
from pydantic import BaseModel, ConfigDict
from typing import Literal


class RegulatoryProductScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_type: Literal[
        "bread",
        "coffee_chicory",
        "milk_product",
        "edible_oil",
        "sweetener_product",
        "other",
    ]
    assessment_date: date


@router.post("/assessment/preview")
def regulatory_product_screening(
    payload: RegulatoryProductScreeningRequest,
    user: AuthenticatedUser,
):
    """Authenticated screening only; no compliance decision."""
    from backend.app.services.regulatory_product_screening import (
        screen_product,
    )
    from backend.app.services.regulatory_registry import RegistryUnavailable

    del user
    try:
        return screen_product(
            payload.product_type,
            payload.assessment_date,
        )
    except RegistryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory registry unavailable",
        ) from exc


# PHASE_3D_BREAD_FACT_SCREENING
from pydantic import Field


class RegulatoryBreadFactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bread_type: Literal[
        "whole_wheat_bread", "wheat_bread", "brown_bread"
    ]
    assessment_date: date
    whole_wheat_flour_percent: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Whole-wheat flour as a percent of total flour",
    )


@router.post("/assessment/bread-facts-preview")
def regulatory_bread_fact_preview(
    payload: RegulatoryBreadFactRequest,
    user: AuthenticatedUser,
):
    from backend.app.services.regulatory_bread_screening import (
        screen_bread_facts,
    )
    from backend.app.services.regulatory_registry import RegistryUnavailable

    del user
    try:
        return screen_bread_facts(
            payload.bread_type,
            payload.whole_wheat_flour_percent,
            payload.assessment_date,
        )
    except RegistryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory registry unavailable",
        ) from exc


# PHASE_3G_DOCUMENT_INTAKE
from fastapi import File, UploadFile
from backend.app.services.regulatory_document_intake import (
    inspect_document, MAX_BYTES
)


@router.post("/documents/preview")
async def regulatory_document_preview(
    user: AuthenticatedUser,
    file: UploadFile = File(...),
):
    """Authenticated, in-memory document inspection only."""
    del user
    try:
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Document exceeds the 8 MB upload limit",
            )
        return inspect_document(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    finally:
        await file.close()


# PHASE_3H_DOCUMENT_EXTRACTION
@router.post("/documents/extract")
async def regulatory_document_extract(
    user: AuthenticatedUser,
    file: UploadFile = File(...),
):
    from backend.app.services.regulatory_document_extraction import (
        extract_regulatory_document,
    )

    del user
    try:
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Document exceeds the 8 MB upload limit",
            )
        return extract_regulatory_document(
            file.filename or "", content
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc)
        ) from exc
    finally:
        await file.close()


# PHASE_3J_LABEL_SCREENING
from datetime import date as RegulatoryScreeningDate
from typing import Literal as RegulatoryLiteral
from fastapi import Form as RegulatoryForm


@router.post("/assessment/label-preview")
async def regulatory_label_assessment_preview(
    user: AuthenticatedUser,
    file: UploadFile = File(...),
    product_type: RegulatoryLiteral[
        "bread",
        "coffee_chicory",
        "milk_product",
        "edible_oil",
        "sweetener_product",
        "other",
    ] = RegulatoryForm(...),
    assessment_date: RegulatoryScreeningDate = RegulatoryForm(...),
):
    """Independent, authenticated, non-persistent label screening."""
    from backend.app.services.regulatory_document_extraction import (
        extract_regulatory_document,
    )
    from backend.app.services.regulatory_label_screening import (
        assess_label_evidence,
    )
    from backend.app.services.regulatory_registry import (
        RegistryUnavailable,
    )

    del user
    try:
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Document exceeds 8 MB",
            )

        document = extract_regulatory_document(
            file.filename or "", content
        )
        return assess_label_evidence(
            document, product_type, assessment_date
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc)
        ) from exc
    except RegistryUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory registry unavailable",
        ) from exc
    finally:
        await file.close()


# PHASE_3L10_BREAD_DRAFT_ENDPOINT
from pathlib import Path as _BreadPath
from fastapi import Body as _bread_body
import hashlib as _bread_hashlib
import json as _bread_json

from backend.app.services.regulatory_bread_draft_calculator import (
    compare_draft_bread,
)

_BREAD_DRAFT_REGISTRY_PATH = (
    _BreadPath(__file__).resolve().parents[4]
    / "data/regulatory/fssai/"
    / "bread_draft_requirements_pending_review_v1.json"
)

_BREAD_DRAFT_REGISTRY_SHA256 = "7bd29281f345973966eed3ea79869545e5775ee8d7f27f0070ef971128f139d2"


@router.post("/assessment/bread-draft-preview")
def regulatory_bread_draft_preview(
    user: AuthenticatedUser,
    payload: dict = _bread_body(...),
):
    """Authenticated numerical preview; never an FSSAI legal verdict."""
    del user

    allowed = {
        "bread_type",
        "ingredient_percent",
        "measurement_basis",
    }

    if set(payload) - allowed:
        raise HTTPException(
            status_code=422,
            detail="Unsupported draft screening input fields",
        )

    bread_type = payload.get("bread_type")
    if not isinstance(bread_type, str) or len(bread_type) > 60:
        raise HTTPException(
            status_code=422,
            detail="Valid bread_type is required",
        )

    if payload.get("measurement_basis") != "100g_flour":
        raise HTTPException(
            status_code=422,
            detail="Measurement basis must be 100g_flour",
        )

    percent = payload.get("ingredient_percent")

    if not (
        percent is None
        or isinstance(percent, (str, int, float, bool))
    ):
        raise HTTPException(
            status_code=422,
            detail="Invalid ingredient percentage type",
        )

    if isinstance(percent, str) and len(percent) > 32:
        raise HTTPException(
            status_code=422,
            detail="Ingredient percentage is too long",
        )

    try:
        raw = _BREAD_DRAFT_REGISTRY_PATH.read_bytes()
    except OSError:
        raise HTTPException(
            status_code=503,
            detail="Draft bread evidence registry unavailable",
        )

    if _bread_hashlib.sha256(raw).hexdigest() != (
        _BREAD_DRAFT_REGISTRY_SHA256
    ):
        raise HTTPException(
            status_code=503,
            detail="Draft bread evidence registry integrity mismatch",
        )

    try:
        draft_registry = _bread_json.loads(raw)
        result = compare_draft_bread(
            draft_registry,
            bread_type,
            percent,
        )
    except (ValueError, KeyError, TypeError) as exc:
        if "Unsupported or ambiguous bread category" in str(exc):
            raise HTTPException(
                status_code=422,
                detail="Unsupported bread category",
            ) from exc
        raise HTTPException(
            status_code=503,
            detail="Draft bread screening registry unavailable",
        ) from exc

    if (
        result.get("rule_executed") is not False
        or result.get("compliance_verdict") is not None
        or result.get("legal_review_complete") is not False
        or result.get("product_facts_verified") is not False
    ):
        raise HTTPException(
            status_code=503,
            detail="Unsafe draft screening result",
        )

    return result
