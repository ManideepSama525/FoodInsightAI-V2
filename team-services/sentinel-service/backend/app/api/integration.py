import os
import secrets

from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    status,
)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fastapi import BackgroundTasks
from app.services.synthetic_ip_auto_response import schedule_containment_after_ingestion
from app.database.database import get_db
from app.models.security_event import SecurityEvent
from app.schemas.integration import SecurityEventIn
from app.services.integration_detection import process_security_event
from app.models.incident import Incident
from app.models.response_action import ResponseAction
from app.models.security_event import SecurityEvent
from datetime import timedelta
from app.schemas.integration import RevokeUserSessionsRequest


router = APIRouter(
    prefix="/integration",
    tags=["Internal Integration"],
)


def verify_ingestion_token(
    x_sentinel_ingest_token: str | None = Header(
        default=None,
        alias="X-Sentinel-Ingest-Token",
    ),
):
    expected = os.getenv("SENTINEL_INGEST_TOKEN")

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security event ingestion is not configured.",
        )

    if (
        not x_sentinel_ingest_token
        or not secrets.compare_digest(
            x_sentinel_ingest_token,
            expected,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid ingestion credentials.",
        )

    return True


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_security_event(
    payload: SecurityEventIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_ingestion_token),
):
    if payload.source != "FoodInsightAI":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported telemetry source.",
        )

    existing = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.event_id == payload.event_id)
        .first()
    )

    if existing:
        return {
            "accepted": True,
            "duplicate": True,
            "event_id": existing.event_id,
            "detections": [],
        }

    occurred = payload.occurred_at or datetime.now(timezone.utc)

    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)

    occurred = occurred.astimezone(timezone.utc).replace(
        tzinfo=None
    )

    received = datetime.now(timezone.utc).replace(
        tzinfo=None
    )

    values = payload.model_dump(
        exclude={"occurred_at"}
    )

    record = SecurityEvent(
        **values,
        occurred_at=occurred,
        received_at=received,
    )

    try:
        db.add(record)
        db.flush()

        # Run stateful detections against recent stored events.
        detections = process_security_event(
            db=db,
            record=record,
        )

        # Persist telemetry and any generated incidents together.
        db.commit()
        db.refresh(record)

    except IntegrityError:
        db.rollback()

        existing = (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.event_id == payload.event_id
            )
            .first()
        )

        if existing:
            return {
                "accepted": True,
                "duplicate": True,
                "event_id": existing.event_id,
                "detections": [],
            }

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security event persistence failed.",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security event processing failed.",
        )


    # SYNTHETIC_IP_AUTO_RESPONSE_STAGE10
    # Only after telemetry and incidents have been committed.
    # Scheduling failures must never corrupt security ingestion.
    try:
        schedule_containment_after_ingestion(
            background_tasks, record, detections
        )
    except Exception:
        import logging
        logging.getLogger(
            "sentinel.synthetic_auto_containment"
        ).exception("Failed to schedule synthetic test containment.")

    return {
        "accepted": True,
        "duplicate": False,
        "event_id": record.event_id,
        "event_db_id": record.id,
        "detections": detections,
    }

def _response_action_result(incident, action_record, duplicate: bool):
    return {
        "accepted": True,
        "incident_id": incident.incident_id,
        "attack_type": incident.attack_type,
        "user_id": action_record.user_id,
        "action_id": action_record.action_id,
        "revoked": True,
        "duplicate": duplicate,
        "previous_token_version": action_record.previous_token_version,
        "new_token_version": action_record.new_token_version,
        "response_status": action_record.status,
        "attempt_count": action_record.attempt_count,
        "incident_response_action": incident.response_action,
    }


def _mark_response_failed(db, action_record, message: str) -> None:
    action_record.status = "FAILED"
    action_record.last_error = message[:300]
    action_record.updated_at = datetime.utcnow()
    try:
        db.commit()
    except Exception:
        db.rollback()


@router.post("/actions/revoke-user-sessions")
def request_revoke_user_sessions(
    payload: RevokeUserSessionsRequest,
    db: Session = Depends(get_db),
    x_sentinel_analyst_token: str | None = Header(default=None, alias="X-Sentinel-Analyst-Token"),
):
    analyst_expected = os.getenv("SENTINEL_ANALYST_ACTION_TOKEN", "")
    if not analyst_expected:
        raise HTTPException(status_code=503, detail="Analyst response authorization is not configured.")
    if not x_sentinel_analyst_token or not secrets.compare_digest(x_sentinel_analyst_token, analyst_expected):
        raise HTTPException(status_code=401, detail="Invalid analyst response credentials.")

    response_token = os.getenv("SENTINEL_RESPONSE_TOKEN", "")
    if not response_token:
        raise HTTPException(status_code=503, detail="FoodInsightAI response channel is not configured.")

    action_id = str(payload.action_id)
    incident = db.query(Incident).filter(Incident.incident_id == str(payload.incident_id)).first()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    action_by_id = db.query(ResponseAction).filter(ResponseAction.action_id == action_id).first()
    action_by_incident = db.query(ResponseAction).filter(ResponseAction.incident_id == incident.incident_id).first()

    if action_by_id is not None and (
        action_by_id.incident_id != incident.incident_id
        or action_by_id.user_id != payload.user_id
    ):
        raise HTTPException(status_code=409, detail="This action ID is already associated with a different response target.")

    if action_by_incident is not None and (
        action_by_incident.action_id != action_id
        or action_by_incident.user_id != payload.user_id
    ):
        raise HTTPException(status_code=409, detail="This incident already has a response action. Retry using its original action ID.")

    # Completed actions are replayed from Sentinel's durable record.
    if action_by_id is not None and action_by_id.status == "SUCCESS":
        if incident.target_user_id != str(payload.user_id):
            raise HTTPException(status_code=409, detail="Completed response target no longer matches incident attribution.")
        return _response_action_result(incident, action_by_id, duplicate=True)

    if incident.status != "Active":
        raise HTTPException(status_code=409, detail="Only active incidents can request session revocation.")
    if incident.attack_type != "Brute Force":
        raise HTTPException(status_code=422, detail="Session revocation is only available for account-attributed brute-force incidents.")
    if incident.response_action == "Session Revoked" and action_by_id is None:
        raise HTTPException(status_code=409, detail="This incident was previously marked revoked but has no retry-safe action record.")

    # Exact account and event evidence. Source IP is corroborating context only.
    if not incident.target_user_id or not incident.target_account_hash or not incident.trigger_event_id:
        raise HTTPException(status_code=422, detail="This incident has no verified single-account trigger event.")
    if incident.target_user_id != str(payload.user_id):
        raise HTTPException(status_code=422, detail="Requested user does not match incident account attribution.")

    trigger_event = db.query(SecurityEvent).filter(
        SecurityEvent.event_id == incident.trigger_event_id,
        SecurityEvent.source == "FoodInsightAI",
        SecurityEvent.event_type == "authentication",
        SecurityEvent.user_id == incident.target_user_id,
        SecurityEvent.account_id_hash == incident.target_account_hash,
        SecurityEvent.source_ip == incident.source_ip,
        SecurityEvent.status_code == 401,
        SecurityEvent.method == "POST",
        SecurityEvent.path.in_(["/auth/login", "/api/v1/auth/login"]),
    ).first()
    if trigger_event is None:
        raise HTTPException(status_code=422, detail="The exact authentication event linked to this incident could not be verified.")

    incident_time = incident.created_at or datetime.utcnow()
    event_time = trigger_event.received_at
    if incident_time.tzinfo is not None:
        incident_time = incident_time.astimezone(timezone.utc).replace(tzinfo=None)
    if event_time.tzinfo is not None:
        event_time = event_time.astimezone(timezone.utc).replace(tzinfo=None)
    if not (incident_time - timedelta(seconds=30) <= event_time <= incident_time + timedelta(seconds=30)):
        raise HTTPException(status_code=422, detail="The linked authentication event falls outside the incident time boundary.")

    evidence_start = event_time - timedelta(seconds=300)
    failed_attempt_count = db.query(SecurityEvent).filter(
        SecurityEvent.source == "FoodInsightAI",
        SecurityEvent.event_type == "authentication",
        SecurityEvent.user_id == incident.target_user_id,
        SecurityEvent.account_id_hash == incident.target_account_hash,
        SecurityEvent.source_ip == incident.source_ip,
        SecurityEvent.status_code == 401,
        SecurityEvent.method == "POST",
        SecurityEvent.path.in_(["/auth/login", "/api/v1/auth/login"]),
        SecurityEvent.received_at >= evidence_start,
        SecurityEvent.received_at <= event_time,
    ).count()
    if failed_attempt_count < 5:
        raise HTTPException(status_code=422, detail="The linked account does not have five verified failed logins in the detector window.")

    # Persist PENDING before the cross-service call. Retries must reuse action_id.
    if action_by_id is None:
        action_record = ResponseAction(
            action_id=action_id,
            incident_id=incident.incident_id,
            user_id=payload.user_id,
            action="revoke_user_sessions",
            status="PENDING",
            attempt_count=1,
            last_error=None,
        )
        db.add(action_record)
        try:
            db.commit()
            db.refresh(action_record)
        except IntegrityError:
            db.rollback()
            action_record = db.query(ResponseAction).filter(ResponseAction.incident_id == incident.incident_id).first()
            if action_record is None or action_record.action_id != action_id or action_record.user_id != payload.user_id:
                raise HTTPException(status_code=409, detail="A different response action was concurrently registered for this incident.")
            if action_record.status == "SUCCESS":
                return _response_action_result(incident, action_record, duplicate=True)
            action_record.status = "PENDING"
            action_record.attempt_count += 1
            action_record.last_error = None
            action_record.updated_at = datetime.utcnow()
            db.commit()
    else:
        action_record = action_by_id
        action_record.status = "PENDING"
        action_record.attempt_count += 1
        action_record.last_error = None
        action_record.updated_at = datetime.utcnow()
        db.commit()

    import httpx
    base_url = os.getenv("FOODINSIGHTAI_INTERNAL_URL", "http://127.0.0.1:8000").rstrip("/")
    endpoint = base_url + "/api/v1/internal/sentinel/revoke-user-sessions"
    request_body = {
        "action_id": action_id,
        "incident_id": incident.incident_id,
        "user_id": payload.user_id,
        "reason": payload.reason[:350] + f" | Evidence event: {trigger_event.event_id}",
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(6.0, connect=2.0)) as client:
            response = client.post(endpoint, json=request_body, headers={"X-Sentinel-Response-Token": response_token})
    except httpx.HTTPError as exc:
        _mark_response_failed(db, action_record, "FoodInsightAI transport error: " + type(exc).__name__)
        raise HTTPException(status_code=502, detail="FoodInsightAI response endpoint is unreachable. Retry using the same action_id.") from exc

    if response.status_code not in (200, 201):
        _mark_response_failed(db, action_record, f"FoodInsightAI returned HTTP {response.status_code}")
        raise HTTPException(status_code=502, detail=f"FoodInsightAI rejected the response action with HTTP {response.status_code}. Investigate, then retry using the same action_id.")

    try:
        result = response.json()
    except ValueError as exc:
        _mark_response_failed(db, action_record, "FoodInsightAI returned invalid JSON")
        raise HTTPException(status_code=502, detail="FoodInsightAI returned an invalid response. Retry using the same action_id.") from exc

    if not isinstance(result, dict) or not result.get("accepted") or not result.get("revoked"):
        _mark_response_failed(db, action_record, "FoodInsightAI did not confirm revocation")
        raise HTTPException(status_code=502, detail="FoodInsightAI did not confirm session revocation. Investigate, then retry using the same action_id.")

    action_record.status = "SUCCESS"
    action_record.previous_token_version = result.get("previous_token_version")
    action_record.new_token_version = result.get("new_token_version")
    action_record.last_error = None
    action_record.updated_at = datetime.utcnow()
    incident.response_action = "Session Revoked"
    db.commit()
    db.refresh(action_record)
    db.refresh(incident)

    return {
        "accepted": True,
        "incident_id": incident.incident_id,
        "attack_type": incident.attack_type,
        "user_id": payload.user_id,
        "trigger_event_id": trigger_event.event_id,
        "verified_failed_attempts": failed_attempt_count,
        "action_id": action_id,
        "revoked": True,
        "duplicate": bool(result.get("duplicate", False)),
        "previous_token_version": action_record.previous_token_version,
        "new_token_version": action_record.new_token_version,
        "response_status": action_record.status,
        "attempt_count": action_record.attempt_count,
        "incident_response_action": incident.response_action,
    }
