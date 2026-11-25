import os
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.models.security_response_action import SecurityResponseAction
from backend.app.schemas.sentinel_response import RevokeUserSessionsRequest

router = APIRouter(prefix="/internal/sentinel", tags=["internal security response"])


def verify_sentinel_response_token(
    x_sentinel_response_token: str | None = Header(default=None, alias="X-Sentinel-Response-Token"),
) -> bool:
    expected = os.getenv("SENTINEL_RESPONSE_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Sentinel response channel is not configured.")
    if not x_sentinel_response_token or not secrets.compare_digest(x_sentinel_response_token, expected):
        raise HTTPException(status_code=401, detail="Invalid response credentials.")
    return True


@router.post("/revoke-user-sessions")
def revoke_user_sessions(
    payload: RevokeUserSessionsRequest,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_sentinel_response_token),
):
    action_id = str(payload.action_id)
    existing = db.scalar(select(SecurityResponseAction).where(SecurityResponseAction.action_id == action_id))
    if existing is not None:
        if existing.target_user_id != payload.user_id or existing.incident_id != payload.incident_id:
            raise HTTPException(status_code=409, detail="Action ID was already used for a different response.")
        return {
            "accepted": True,
            "revoked": True,
            "duplicate": True,
            "action_id": existing.action_id,
            "incident_id": existing.incident_id,
            "user_id": existing.target_user_id,
            "previous_token_version": existing.previous_token_version,
            "new_token_version": existing.new_token_version,
        }

    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Target FoodInsightAI user was not found.")

    previous_version = int(user.token_version)
    new_version = previous_version + 1
    user.token_version = new_version
    record = SecurityResponseAction(
        action_id=action_id,
        incident_id=payload.incident_id,
        action="revoke_user_sessions",
        target_user_id=user.id,
        reason=payload.reason,
        performed_by="Sentinel-XDR",
        previous_token_version=previous_version,
        new_token_version=new_version,
        result="SUCCESS",
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(SecurityResponseAction).where(SecurityResponseAction.action_id == action_id))
        if existing is not None and existing.target_user_id == payload.user_id and existing.incident_id == payload.incident_id:
            return {
                "accepted": True,
                "revoked": True,
                "duplicate": True,
                "action_id": existing.action_id,
                "incident_id": existing.incident_id,
                "user_id": existing.target_user_id,
                "previous_token_version": existing.previous_token_version,
                "new_token_version": existing.new_token_version,
            }
        raise HTTPException(status_code=409, detail="Response action could not be recorded safely.")

    return {
        "accepted": True,
        "revoked": True,
        "duplicate": False,
        "action_id": action_id,
        "incident_id": payload.incident_id,
        "user_id": user.id,
        "previous_token_version": previous_version,
        "new_token_version": new_version,
    }


# SECURITY_IP_CONTAINMENT_STAGE2
# Restricted test-network containment, separate from session revocation.
from backend.app.schemas.security_ip_block import TemporaryIPBlockRequest
from backend.app.services.security_ip_containment import (
    create_temporary_ip_block,
)


@router.post("/temporary-ip-block")
def create_sentinel_temporary_ip_block(
    payload: TemporaryIPBlockRequest,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_sentinel_response_token),
):
    """Persist an authenticated synthetic-IP block, without firewall changes."""
    del authorized

    try:
        result = create_temporary_ip_block(
            db,
            action_id=str(payload.action_id),
            incident_id=payload.incident_id,
            source_ip=payload.source_ip,
            duration_seconds=payload.duration_seconds,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return {
        **result,
        "enforcement_scope": "SYNTHETIC_TEST_IP_ONLY",
        "firewall_modified": False,
        "middleware_enforcement_verified": False,
    }
