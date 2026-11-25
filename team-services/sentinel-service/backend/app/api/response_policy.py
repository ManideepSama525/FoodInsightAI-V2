import os
import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.incident import Incident
from app.models.response_action import ResponseAction
from app.models.response_policy_decision import ResponsePolicyDecision
from app.services.response_policy import (
    POLICY_VERSION,
    collect_bruteforce_evidence,
    evaluate_response_policy,
)


router = APIRouter(
    prefix="/response-policy",
    tags=["Response Policy"],
)


@router.post("/incidents/{incident_id}/evaluate")
def evaluate_incident_policy(
    incident_id: str,
    db: Session = Depends(get_db),
    x_sentinel_analyst_token: str | None = Header(
        default=None,
        alias="X-Sentinel-Analyst-Token",
    ),
):
    """Persist an analyst-authorized policy evaluation without executing it."""

    expected = os.getenv("SENTINEL_ANALYST_ACTION_TOKEN", "")

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Analyst policy authorization is not configured.",
        )

    if (
        not x_sentinel_analyst_token
        or not secrets.compare_digest(x_sentinel_analyst_token, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid analyst policy credentials.",
        )

    incident = (
        db.query(Incident)
        .filter(Incident.incident_id == incident_id)
        .first()
    )

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    existing_action = (
        db.query(ResponseAction)
        .filter(ResponseAction.incident_id == incident.incident_id)
        .first()
    )

    evidence = collect_bruteforce_evidence(db, incident)

    decision = evaluate_response_policy(
        incident=incident,
        evidence=evidence,
        response_action_exists=existing_action is not None,
    )

    evaluation_id = str(uuid.uuid4())

    record = ResponsePolicyDecision(
        evaluation_id=evaluation_id,
        incident_id=incident.incident_id,
        policy_version=POLICY_VERSION,
        decision=decision["decision"],
        recommended_action=decision["recommended_action"],
        severity=decision["severity"],
        confidence_score=decision["confidence_score"],
        evidence_count=decision["evidence_count"],
        evidence_verified=decision["evidence_verified"],
        requires_approval=decision["requires_approval"],
        automation_authorized=False,
        execution_mode="DRY_RUN",
        trigger_event_id=decision["trigger_event_id"],
        reason=decision["reason"],
        actor="authorized_request",
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Policy evaluation audit could not be persisted.",
        )

    return {
        "accepted": True,
        "evaluation_id": record.evaluation_id,
        "incident_id": record.incident_id,
        **decision,
        "audit_recorded": True,
        "action_executed": False,
    }

# ---------------------------------------------------------------------------
# Stage 2E: explicit analyst approval and retry-safe response integration.
# This endpoint is intentionally separate from dry-run policy evaluation.
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from uuid import UUID


class ApproveResponseRequest(BaseModel):
    action_id: UUID
    approval_reason: str = Field(min_length=10, max_length=250)


@router.post("/evaluations/{evaluation_id}/approve")
def approve_policy_response(
    evaluation_id: str,
    payload: ApproveResponseRequest,
    db: Session = Depends(get_db),
    x_sentinel_analyst_token: str | None = Header(
        default=None,
        alias="X-Sentinel-Analyst-Token",
    ),
):
    """Record explicit analyst approval and invoke the existing guarded route."""

    import os
    import httpx

    from sqlalchemy.exc import IntegrityError

    from app.models.response_approval import ResponseApproval
    from app.schemas.integration import RevokeUserSessionsRequest
    from app.services.response_approval import validate_approval_request

    expected = os.getenv("SENTINEL_ANALYST_ACTION_TOKEN", "")

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Analyst response authorization is not configured.",
        )

    if (
        not x_sentinel_analyst_token
        or not secrets.compare_digest(x_sentinel_analyst_token, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid analyst approval credentials.",
        )

    decision_record = (
        db.query(ResponsePolicyDecision)
        .filter(ResponsePolicyDecision.evaluation_id == evaluation_id)
        .first()
    )

    if decision_record is None:
        raise HTTPException(status_code=404, detail="Policy evaluation not found.")

    incident = (
        db.query(Incident)
        .filter(Incident.incident_id == decision_record.incident_id)
        .first()
    )

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    action_id = str(payload.action_id)
    approval_reason = payload.approval_reason.strip()

    if len(approval_reason) < 10:
        raise HTTPException(
            status_code=422,
            detail="An approval reason of at least 10 characters is required.",
        )

    approval = (
        db.query(ResponseApproval)
        .filter(ResponseApproval.evaluation_id == evaluation_id)
        .first()
    )

    approval_for_incident = (
        db.query(ResponseApproval)
        .filter(ResponseApproval.incident_id == incident.incident_id)
        .first()
    )

    action_by_id = (
        db.query(ResponseAction)
        .filter(ResponseAction.action_id == action_id)
        .first()
    )

    action_by_incident = (
        db.query(ResponseAction)
        .filter(ResponseAction.incident_id == incident.incident_id)
        .first()
    )

    # An approval is immutable: retries must reuse its evaluation, action ID,
    # account, and original reason.
    if approval is not None:
        if (
            approval.action_id != action_id
            or approval.incident_id != incident.incident_id
            or approval.approval_reason != approval_reason
        ):
            raise HTTPException(
                status_code=409,
                detail="Approval retry must reuse the original action ID and reason.",
            )

    if approval_for_incident is not None:
        if (
            approval is None
            or approval_for_incident.evaluation_id != evaluation_id
            or approval_for_incident.action_id != action_id
        ):
            raise HTTPException(
                status_code=409,
                detail="This incident already has a different approval record.",
            )

    if action_by_id is not None:
        if (
            action_by_id.incident_id != incident.incident_id
            or str(action_by_id.user_id) != str(incident.target_user_id)
        ):
            raise HTTPException(
                status_code=409,
                detail="Action ID is already associated with a different response target.",
            )

    if action_by_incident is not None:
        if (
            approval is None
            or action_by_incident.action_id != action_id
            or str(action_by_incident.user_id) != str(incident.target_user_id)
        ):
            raise HTTPException(
                status_code=409,
                detail="An unapproved or different response action already exists.",
            )

    if approval is not None and approval.status == "SUCCESS":
        if action_by_id is None or action_by_id.status != "SUCCESS":
            raise HTTPException(
                status_code=409,
                detail="Approval is marked successful but its response record is inconsistent.",
            )

        return {
            "accepted": True,
            "duplicate": True,
            "approval_status": "SUCCESS",
            "evaluation_id": evaluation_id,
            "incident_id": incident.incident_id,
            "action_id": action_id,
            "user_id": action_by_id.user_id,
            "revoked": True,
            "action_executed": False,
            "execution_mode": "REPLAY_OF_CONFIRMED_ACTION",
            "previous_token_version": action_by_id.previous_token_version,
            "new_token_version": action_by_id.new_token_version,
        }

    now = datetime.utcnow()

    if approval is not None and approval.status == "EXECUTING":
        updated = approval.updated_at
        if updated is not None and updated.tzinfo is not None:
            updated = updated.astimezone(timezone.utc).replace(tzinfo=None)

        if updated is not None and (now - updated).total_seconds() < 120:
            raise HTTPException(
                status_code=409,
                detail="This approved action is already being processed. Retry later with the same action ID.",
            )

    # A pre-existing manual action cannot be retroactively treated as approved.
    if approval is None and action_by_incident is not None:
        raise HTTPException(
            status_code=409,
            detail="A response action already exists without this approval record.",
        )

    # Recheck current evidence immediately before a new execution or retry.
    evidence = collect_bruteforce_evidence(db, incident)

    # The only existing action permitted here is the one linked to this same
    # approval. It is not treated as a competing action on a retry.
    current_decision = evaluate_response_policy(
        incident=incident,
        evidence=evidence,
        response_action_exists=False,
    )

    eligibility = validate_approval_request(
        policy_record=decision_record,
        incident=incident,
        evidence=evidence,
        current_decision=current_decision,
        now=now,
        max_age_seconds=600 if approval is None else None,
    )

    if not eligibility["eligible"]:
        raise HTTPException(
            status_code=409,
            detail="Approval rejected: " + eligibility["reason"],
        )

    try:
        user_id = int(incident.target_user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="Incident target user ID is not a valid numeric account ID.",
        )

    if user_id <= 0 or str(user_id) != str(incident.target_user_id):
        raise HTTPException(
            status_code=422,
            detail="Incident target user ID is not in canonical numeric form.",
        )

    if approval is None:
        approval = ResponseApproval(
            evaluation_id=evaluation_id,
            action_id=action_id,
            incident_id=incident.incident_id,
            user_id=user_id,
            status="APPROVED_PENDING",
            attempt_count=0,
            approved_by="authorized_analyst_token",
            approval_reason=approval_reason,
            last_error=None,
            approved_at=now,
            updated_at=now,
        )

        db.add(approval)

        try:
            db.commit()
            db.refresh(approval)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="A concurrent approval was registered. Retry with the same evaluation and action ID.",
            )

    # Persist the execution attempt before calling the existing endpoint.
    approval.status = "EXECUTING"
    approval.attempt_count += 1
    approval.last_error = None
    approval.updated_at = now

    try:
        db.commit()
        db.refresh(approval)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Approval execution state could not be persisted.",
        )

    # Construct the exact request model expected by the existing guarded
    # revocation endpoint. That endpoint rechecks the linked evidence and
    # performs its own action-ID idempotency checks.
    downstream_reason = (
        approval_reason[:160]
        + " | Evaluation: "
        + evaluation_id
        + " | Trigger: "
        + str(incident.trigger_event_id)
    )

    try:
        downstream_payload = RevokeUserSessionsRequest(
            action_id=action_id,
            incident_id=incident.incident_id,
            user_id=user_id,
            reason=downstream_reason,
        )
        if hasattr(downstream_payload, "model_dump"):
            request_body = downstream_payload.model_dump(mode="json")
        else:
            request_body = downstream_payload.dict()
    except Exception:
        approval.status = "FAILED"
        approval.last_error = "Existing response request schema validation failed."
        approval.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(
            status_code=422,
            detail="The existing response request schema rejected the approval payload.",
        )

    base_url = os.getenv(
        "SENTINEL_INTERNAL_BASE_URL",
        "http://127.0.0.1:8010",
    ).rstrip("/")

    try:
        with httpx.Client(
            timeout=httpx.Timeout(10.0, connect=2.0)
        ) as client:
            response = client.post(
                base_url + "/integration/actions/revoke-user-sessions",
                json=request_body,
                headers={
                    "X-Sentinel-Analyst-Token": expected,
                },
            )
    except httpx.HTTPError as exc:
        approval.status = "FAILED"
        approval.last_error = "Existing response endpoint transport error: " + type(exc).__name__
        approval.updated_at = datetime.utcnow()
        db.commit()

        raise HTTPException(
            status_code=502,
            detail="Existing response endpoint could not be reached. Retry with the same action ID.",
        ) from exc

    if response.status_code not in (200, 201):
        approval.status = "FAILED"
        approval.last_error = (
            "Existing response endpoint returned HTTP "
            + str(response.status_code)
        )[:300]
        approval.updated_at = datetime.utcnow()
        db.commit()

        raise HTTPException(
            status_code=502,
            detail=(
                "Existing response endpoint rejected the action with HTTP "
                + str(response.status_code)
                + ". Investigate and retry using the same action ID."
            ),
        )

    try:
        result = response.json()
    except ValueError as exc:
        approval.status = "FAILED"
        approval.last_error = "Existing response endpoint returned invalid JSON."
        approval.updated_at = datetime.utcnow()
        db.commit()

        raise HTTPException(
            status_code=502,
            detail="Existing response endpoint returned an invalid response.",
        ) from exc

    if (
        not isinstance(result, dict)
        or result.get("accepted") is not True
        or result.get("revoked") is not True
        or str(result.get("action_id")) != action_id
    ):
        approval.status = "FAILED"
        approval.last_error = "Existing response endpoint did not confirm the requested action."
        approval.updated_at = datetime.utcnow()
        db.commit()

        raise HTTPException(
            status_code=502,
            detail="The existing response endpoint did not confirm the requested action.",
        )

    approval.status = "SUCCESS"
    approval.last_error = None
    approval.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(approval)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "The response endpoint confirmed the action, but the approval "
                "audit update failed. Retry with the same action ID."
            ),
        )

    return {
        "accepted": True,
        "duplicate": bool(result.get("duplicate", False)),
        "approval_recorded": True,
        "approval_status": approval.status,
        "evaluation_id": evaluation_id,
        "incident_id": incident.incident_id,
        "action_id": action_id,
        "user_id": user_id,
        "revoked": True,
        "action_executed": True,
        "execution_mode": "ANALYST_APPROVED",
        "automation_authorized": False,
        "approval_attempt_count": approval.attempt_count,
        "response": result,
    }

# STAGE2G_READ_ONLY_RESPONSE_AUDIT
@router.get("/audit")
def get_response_audit(
    incident_id: str | None = None,
    status: str | None = None,
    record_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    x_sentinel_analyst_token: str | None = Header(
        default=None,
        alias="X-Sentinel-Analyst-Token",
    ),
):
    """Return a read-only, paginated response audit feed."""

    import os
    import re

    from sqlalchemy import func, literal, select, union_all

    from app.models.response_approval import ResponseApproval

    expected = os.getenv("SENTINEL_ANALYST_ACTION_TOKEN", "")

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Analyst audit authorization is not configured.",
        )

    if (
        not x_sentinel_analyst_token
        or not secrets.compare_digest(x_sentinel_analyst_token, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid analyst audit credentials.",
        )

    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=422,
            detail="Audit page size must be between 1 and 100.",
        )

    if not 0 <= offset <= 50000:
        raise HTTPException(
            status_code=422,
            detail="Audit offset is outside the permitted range.",
        )

    if incident_id is not None and not re.fullmatch(
        r"[A-Za-z0-9_-]{1,20}", incident_id
    ):
        raise HTTPException(
            status_code=422,
            detail="Invalid incident ID filter.",
        )

    allowed_types = {
        "POLICY_EVALUATION",
        "ANALYST_APPROVAL",
        "RESPONSE_ACTION",
    }

    if record_type is not None and record_type not in allowed_types:
        raise HTTPException(
            status_code=422,
            detail="Unsupported audit record type.",
        )

    if status is not None and (
        len(status) > 48
        or not re.fullmatch(r"[A-Za-z0-9_ -]{1,48}", status)
    ):
        raise HTTPException(
            status_code=422,
            detail="Invalid audit status filter.",
        )

    # Normalize all three existing tables into one read-only feed.
    policy_rows = select(
        literal("POLICY_EVALUATION").label("record_type"),
        ResponsePolicyDecision.id.label("record_id"),
        ResponsePolicyDecision.created_at.label("occurred_at"),
        ResponsePolicyDecision.incident_id.label("incident_id"),
        ResponsePolicyDecision.evaluation_id.label("evaluation_id"),
        literal(None).label("action_id"),
        ResponsePolicyDecision.decision.label("status"),
        ResponsePolicyDecision.recommended_action.label("action"),
        ResponsePolicyDecision.actor.label("actor"),
        ResponsePolicyDecision.reason.label("summary"),
        ResponsePolicyDecision.evidence_count.label("evidence_count"),
        ResponsePolicyDecision.evidence_verified.label("evidence_verified"),
        ResponsePolicyDecision.execution_mode.label("execution_mode"),
        literal(None).label("attempt_count"),
        literal(None).label("last_error"),
    )

    approval_rows = select(
        literal("ANALYST_APPROVAL").label("record_type"),
        ResponseApproval.id.label("record_id"),
        ResponseApproval.approved_at.label("occurred_at"),
        ResponseApproval.incident_id.label("incident_id"),
        ResponseApproval.evaluation_id.label("evaluation_id"),
        ResponseApproval.action_id.label("action_id"),
        ResponseApproval.status.label("status"),
        literal("REVOKE_USER_SESSIONS").label("action"),
        ResponseApproval.approved_by.label("actor"),
        ResponseApproval.approval_reason.label("summary"),
        literal(None).label("evidence_count"),
        literal(None).label("evidence_verified"),
        literal("ANALYST_APPROVED").label("execution_mode"),
        ResponseApproval.attempt_count.label("attempt_count"),
        ResponseApproval.last_error.label("last_error"),
    )

    action_rows = select(
        literal("RESPONSE_ACTION").label("record_type"),
        ResponseAction.id.label("record_id"),
        ResponseAction.updated_at.label("occurred_at"),
        ResponseAction.incident_id.label("incident_id"),
        literal(None).label("evaluation_id"),
        ResponseAction.action_id.label("action_id"),
        ResponseAction.status.label("status"),
        ResponseAction.action.label("action"),
        literal("response_service").label("actor"),
        literal("Account-specific response action lifecycle record").label("summary"),
        literal(None).label("evidence_count"),
        literal(None).label("evidence_verified"),
        literal("ACCOUNT_SESSION_RESPONSE").label("execution_mode"),
        ResponseAction.attempt_count.label("attempt_count"),
        ResponseAction.last_error.label("last_error"),
    )

    feed = union_all(
        policy_rows,
        approval_rows,
        action_rows,
    ).subquery("response_audit_feed")

    statement = select(feed)

    if incident_id is not None:
        statement = statement.where(feed.c.incident_id == incident_id)

    if status is not None:
        statement = statement.where(
            func.lower(feed.c.status) == status.strip().lower()
        )

    if record_type is not None:
        statement = statement.where(feed.c.record_type == record_type)

    total = db.execute(
        select(func.count()).select_from(statement.subquery())
    ).scalar() or 0

    rows = db.execute(
        statement
        .order_by(
            feed.c.occurred_at.desc(),
            feed.c.record_type.asc(),
            feed.c.record_id.desc(),
        )
        .offset(offset)
        .limit(limit)
    ).mappings().all()

    items = []

    for row in rows:
        item = dict(row)
        timestamp = item.get("occurred_at")

        if timestamp is not None and hasattr(timestamp, "isoformat"):
            item["occurred_at"] = timestamp.isoformat()

        items.append(item)

    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
        "read_only": True,
    }

# ------------------------------------------------------------------
# STAGE2H_PROTECTED_RESPONSE_ANALYTICS
# Read-only, aggregated security response analytics.
# No user identifiers, account hashes or raw security events returned.
# ------------------------------------------------------------------

@router.get("/analytics")
def response_analytics(
    db: Session = Depends(get_db),
    x_sentinel_analyst_token: str | None = Header(
        default=None,
        alias="X-Sentinel-Analyst-Token",
    ),
):
    from datetime import datetime, timezone
    from sqlalchemy import func

    from app.models.response_approval import ResponseApproval
    from app.models.security_event import SecurityEvent

    expected = os.getenv("SENTINEL_ANALYST_ACTION_TOKEN", "")

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Analyst analytics authorization is not configured.",
        )

    if (
        not x_sentinel_analyst_token
        or not secrets.compare_digest(x_sentinel_analyst_token, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid analyst analytics credentials.",
        )

    def count_rows(model):
        return int(
            db.query(func.count(model.id)).scalar() or 0
        )

    def grouped_counts(model, field):
        rows = (
            db.query(field, func.count(model.id))
            .group_by(field)
            .all()
        )

        return {
            str(key or "UNKNOWN").upper(): int(value)
            for key, value in rows
        }

    # Policy decision statistics.
    total_evaluations = count_rows(ResponsePolicyDecision)

    required_approval_evaluations = (
        db.query(func.count(ResponsePolicyDecision.id))
        .filter(ResponsePolicyDecision.requires_approval.is_(True))
        .scalar() or 0
    )

    policy_breakdown = grouped_counts(
        ResponsePolicyDecision,
        ResponsePolicyDecision.decision,
    )

    # Analyst approval statistics.
    total_approvals = count_rows(ResponseApproval)

    approval_breakdown = grouped_counts(
        ResponseApproval,
        ResponseApproval.status,
    )

    # Actual response-action outcomes.
    total_actions = count_rows(ResponseAction)

    action_breakdown = grouped_counts(
        ResponseAction,
        ResponseAction.status,
    )

    success_actions = (
        db.query(func.count(ResponseAction.id))
        .filter(func.upper(ResponseAction.status) == "SUCCESS")
        .scalar() or 0
    )

    failed_actions = (
        db.query(func.count(ResponseAction.id))
        .filter(func.upper(ResponseAction.status) == "FAILED")
        .scalar() or 0
    )

    completed_actions = success_actions + failed_actions

    pending_actions = max(
        0,
        total_actions - completed_actions,
    )

    success_rate = (
        round((success_actions / completed_actions) * 100, 1)
        if completed_actions > 0
        else None
    )

    # Separate actions linked to the Stage 2E approval workflow
    # from historical or otherwise unlinked response actions.
    def count_approval_linked_actions(action_status=None):
        query = (
            db.query(func.count(ResponseAction.id))
            .join(
                ResponseApproval,
                ResponseApproval.incident_id == ResponseAction.incident_id,
            )
            .filter(ResponseApproval.action_id == ResponseAction.action_id)
        )

        if action_status is not None:
            query = query.filter(
                func.upper(ResponseAction.status) == action_status
            )

        return int(query.scalar() or 0)

    approval_linked_actions = count_approval_linked_actions()
    approval_linked_successes = count_approval_linked_actions("SUCCESS")
    approval_linked_failures = count_approval_linked_actions("FAILED")

    approval_linked_completed = (
        approval_linked_successes + approval_linked_failures
    )

    approval_linked_success_rate = (
        round(
            (approval_linked_successes / approval_linked_completed) * 100,
            1,
        )
        if approval_linked_completed > 0
        else None
    )

    actions_without_approval = max(
        0,
        total_actions - approval_linked_actions,
    )

    unlinked_successful_actions = max(
        0,
        success_actions - approval_linked_successes,
    )

    unlinked_failed_actions = max(
        0,
        failed_actions - approval_linked_failures,
    )
    approval_coverage = (
        round(
            (total_approvals / required_approval_evaluations) * 100,
            1,
        )
        if required_approval_evaluations > 0
        else None
    )

    # Incident and security-event correlation.
    linked_incidents = (
        db.query(func.count(Incident.id))
        .filter(Incident.trigger_event_id.isnot(None))
        .scalar() or 0
    )

    exact_event_matches = (
        db.query(func.count(Incident.id))
        .join(
            SecurityEvent,
            SecurityEvent.event_id == Incident.trigger_event_id,
        )
        .filter(Incident.trigger_event_id.isnot(None))
        .scalar() or 0
    )

    # Strong account-attribution correlation:
    # trigger ID, user ID, account hash, source IP and authentication event.
    verified_account_matches = (
        db.query(func.count(Incident.id))
        .join(
            SecurityEvent,
            SecurityEvent.event_id == Incident.trigger_event_id,
        )
        .filter(
            Incident.trigger_event_id.isnot(None),
            Incident.target_user_id.isnot(None),
            Incident.target_account_hash.isnot(None),
            SecurityEvent.source == "FoodInsightAI",
            SecurityEvent.event_type == "authentication",
            SecurityEvent.user_id == Incident.target_user_id,
            SecurityEvent.account_id_hash == Incident.target_account_hash,
            SecurityEvent.source_ip == Incident.source_ip,
            SecurityEvent.status_code == 401,
            SecurityEvent.method == "POST",
            SecurityEvent.path.in_(
                ("/auth/login", "/api/v1/auth/login")
            ),
        )
        .scalar() or 0
    )

    incidents_without_event = max(
        0,
        linked_incidents - exact_event_matches,
    )

    matched_but_unverified = max(
        0,
        exact_event_matches - verified_account_matches,
    )

    severity_breakdown = grouped_counts(
        Incident,
        Incident.severity,
    )

    total_events = count_rows(SecurityEvent)
    total_incidents = count_rows(Incident)

    return {
        "schema_version": "2H.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "metrics": {
            "total_incidents": total_incidents,
            "total_security_events": total_events,
            "total_policy_evaluations": total_evaluations,
            "requires_analyst_approval": int(
                required_approval_evaluations
            ),
            "total_approval_records": total_approvals,
            "approval_record_coverage_pct": approval_coverage,
            "total_response_actions": total_actions,
            "successful_actions": int(success_actions),
            "failed_actions": int(failed_actions),
            "pending_actions": int(pending_actions),
            "completed_action_success_rate_pct": success_rate,
            "actions_with_approval_record": approval_linked_actions,
            "actions_without_approval_record": actions_without_approval,
            "approval_linked_successful_actions": approval_linked_successes,
            "approval_linked_failed_actions": approval_linked_failures,
            "approval_linked_success_rate_pct": approval_linked_success_rate,
            "unlinked_successful_actions": unlinked_successful_actions,
            "unlinked_failed_actions": unlinked_failed_actions,
        },
        "correlation": {
            "incidents_with_trigger_event": int(linked_incidents),
            "exact_trigger_event_matches": int(exact_event_matches),
            "verified_account_correlations": int(
                verified_account_matches
            ),
            "unmatched_trigger_events": int(incidents_without_event),
            "matched_but_unverified_attributions": int(
                matched_but_unverified
            ),
        },
        "breakdowns": {
            "policy_decisions": policy_breakdown,
            "approval_statuses": approval_breakdown,
            "response_action_statuses": action_breakdown,
            "incident_severities": severity_breakdown,
        },
    }


# SYNTHETIC_IP_CONTAINMENT_AUDIT_STAGE9
@router.get("/synthetic-ip-containment/audit")
def get_synthetic_ip_containment_audit(
    incident_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    x_sentinel_analyst_token: str | None = Header(
        default=None,
        alias="X-Sentinel-Analyst-Token",
    ),
):
    """Protected read-only containment audit; never executes responses."""
    import re
    from sqlalchemy import func
    from app.models.synthetic_ip_containment_action import (
        SyntheticIPContainmentAction,
    )

    expected = os.getenv("SENTINEL_ANALYST_ACTION_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Analyst authorization not configured.",
        )

    if (
        not x_sentinel_analyst_token
        or not secrets.compare_digest(
            x_sentinel_analyst_token, expected
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid analyst credentials.",
        )

    if not 1 <= limit <= 100 or not 0 <= offset <= 50000:
        raise HTTPException(
            status_code=422,
            detail="Invalid audit pagination.",
        )

    if incident_id is not None and not re.fullmatch(
        r"INC-\d{6}", incident_id
    ):
        raise HTTPException(
            status_code=422,
            detail="Invalid incident filter.",
        )

    query = db.query(SyntheticIPContainmentAction)

    if incident_id is not None:
        query = query.filter(
            SyntheticIPContainmentAction.incident_id == incident_id
        )

    total = query.count()

    rows = (
        query.order_by(
            SyntheticIPContainmentAction.created_at.desc(),
            SyntheticIPContainmentAction.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []
    for record in rows:
        items.append({
            "action_id": record.action_id,
            "incident_id": record.incident_id,
            "source_ip": record.source_ip,
            "action": "TEMPORARY_IP_BLOCK",
            "status": record.status,
            "duration_seconds": record.duration_seconds,
            "attempt_count": record.attempt_count,
            "confirmed_expires_at": (
                record.confirmed_expires_at.isoformat() + "Z"
                if record.confirmed_expires_at else None
            ),
            "created_at": (
                record.created_at.isoformat()
                if record.created_at else None
            ),
            "updated_at": (
                record.updated_at.isoformat()
                if record.updated_at else None
            ),
            "last_error": record.last_error,
            "target_confirmation_recorded": (
                record.status == "SUCCESS"
            ),
            "middleware_enforcement_verified": False,
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
        "read_only": True,
        "execution_enabled_by_audit": False,
    }
