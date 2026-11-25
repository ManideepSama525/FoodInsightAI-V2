from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.security_event import SecurityEvent
from app.models.incident import Incident

from app.detectors.bruteforce_detector import (
    detect_bruteforce,
    detect_credential_stuffing,
)

from app.detectors.api_detector import detect_api_abuse

from app.ai.correlation_engine import correlate_incident
from app.ai.threat_scoring import calculate_threat_score
from app.ai.response_engine import generate_ai_response


HISTORY_SECONDS = 300
INCIDENT_DEDUPE_SECONDS = 300
MAX_HISTORY_EVENTS = 500
PAYLOAD_INDICATOR_RULES = {
    "FOOD_SQLI_001": ("SQL Injection", "A SQL injection indicator was matched locally by FoodInsightAI."),
    "FOOD_XSS_001": ("Cross Site Scripting", "A cross-site scripting indicator was matched locally by FoodInsightAI."),
    "FOOD_CMDI_001": ("Command Injection", "A command injection indicator was matched locally by FoodInsightAI."),
    "FOOD_PATH_001": ("Directory Traversal", "A directory traversal indicator was matched locally by FoodInsightAI."),
}


def _payload_indicator_detection(record: SecurityEvent):
    if record.source != "FoodInsightAI" or record.event_type != "payload_security":
        return None

    mapped = PAYLOAD_INDICATOR_RULES.get(record.detection_rule_id or "")
    if mapped is None:
        return None

    attack_type, explanation = mapped
    return {
        "detected": True,
        "attack": attack_type,
        "severity": "High",
        "confidence": 85.0,
        "rule_confidence": 85.0,
        "matched_rule": record.detection_rule_id,
        "explanation": explanation + " Request content was not transmitted.",
        "action": "MONITOR",
    }



def _event_dict(record):
    return {
        "event_type": record.event_type,
        "timestamp": record.received_at,
        "client_id": record.client_id,
        "source_ip": record.source_ip,
        "account_id_hash": record.account_id_hash,
        "method": record.method,
        "path": record.path,
        "status_code": record.status_code,
    }


def _load_history(db: Session, record: SecurityEvent, now: datetime):
    cutoff = now - timedelta(seconds=HISTORY_SECONDS)

    query = db.query(SecurityEvent).filter(
        SecurityEvent.id != record.id,
        SecurityEvent.received_at >= cutoff,
    )

    if record.client_id:
        query = query.filter(
            SecurityEvent.client_id == record.client_id
        )
    else:
        query = query.filter(
            SecurityEvent.source_ip == record.source_ip
        )

    rows = (
        query.order_by(SecurityEvent.received_at.desc())
        .limit(MAX_HISTORY_EVENTS)
        .all()
    )

    return [_event_dict(item) for item in rows]


def _find_existing_incident(
    db: Session,
    attack_type: str,
    source_ip: str,
    now: datetime,
    target_user_id: str | None = None,
    target_account_hash: str | None = None,
):
    cutoff = now - timedelta(seconds=INCIDENT_DEDUPE_SECONDS)

    query = db.query(Incident).filter(
        Incident.attack_type == attack_type,
        Incident.status == "Active",
        Incident.created_at >= cutoff,
    )

    if attack_type == "Brute Force":
        # A shared Docker/network IP is not an account identity. Keep
        # brute-force incidents separate for each pseudonymous account.
        if target_user_id is None:
            query = query.filter(Incident.target_user_id.is_(None))
        else:
            query = query.filter(Incident.target_user_id == target_user_id)

        if target_account_hash is None:
            query = query.filter(Incident.target_account_hash.is_(None))
        else:
            query = query.filter(
                Incident.target_account_hash == target_account_hash
            )
    else:
        query = query.filter(Incident.source_ip == source_ip)

    return query.order_by(Incident.id.desc()).first()


def _create_incident(
    db: Session,
    record: SecurityEvent,
    detection: dict,
    now: datetime,
):
    attack_type = detection["attack"]
    severity = detection["severity"]
    source_ip = record.source_ip or "unknown"

    target_user_id = None
    target_account_hash = None
    trigger_event_id = None

    if attack_type == "Brute Force":
        target_user_id = str(record.user_id)[:64] if record.user_id else None
        target_account_hash = record.account_id_hash
        if (
            record.source == "FoodInsightAI"
            and record.event_type == "authentication"
            and record.status_code == 401
            and record.method == "POST"
            and (record.path or "").rstrip("/")
                in {"/auth/login", "/api/v1/auth/login"}
            and target_user_id
            and target_account_hash
        ):
            trigger_event_id = record.event_id

    existing = _find_existing_incident(
        db,
        attack_type,
        source_ip,
        now,
        target_user_id=target_user_id,
        target_account_hash=target_account_hash,
    )

    if existing:
        return {
            "attack": attack_type,
            "matched_rule": detection.get("matched_rule"),
            "incident_id": existing.incident_id,
            "created": False,
            "action_code": "MONITOR",
        }

    rule_confidence = float(
        detection.get(
            "rule_confidence",
            detection.get("confidence", 0),
        )
    )

    campaign = correlate_incident(
        db=db,
        source_ip=source_ip,
        attack_type=attack_type,
    )

    # No AI model confidence is assumed for these
    # historical rule-based detections.
    threat_score = calculate_threat_score(
        severity=severity,
        ai_confidence=0,
        campaign=campaign["campaign"],
        frequency=campaign["incident_count"],
    )

    response = generate_ai_response(
        attack_type=attack_type,
        severity=severity,
        confidence=0,
        rule_confidence=rule_confidence,
    )

    max_id = db.query(func.max(Incident.id)).scalar() or 0
    incident_number = f"INC-{int(max_id) + 1:06d}"

    explanation = detection.get(
        "explanation",
        "Suspicious activity identified through historical telemetry.",
    )

    incident = Incident(
        incident_id=incident_number,
        attack_type=attack_type,
        severity=severity,
        source_ip=source_ip,
        target=(record.path or "Unknown")[:255],
        description=explanation,
        ai_explanation=explanation,
        confidence=rule_confidence,
        ai_prediction=None,
        ai_confidence=0,
        ai_model="Sentinel-XDR Stateful Rule Engine",
        threat_score=threat_score,
        response_action=response["action"],
        status="Active",
        acknowledged=False,
        target_user_id=target_user_id,
        target_account_hash=target_account_hash,
        trigger_event_id=trigger_event_id,
        created_at=now,
    )

    db.add(incident)
    db.flush()

    return {
        "attack": attack_type,
        "matched_rule": detection.get("matched_rule"),
        "incident_id": incident.incident_id,
        "created": True,
        "severity": severity,
        "threat_score": threat_score,
        "action_code": response["action_code"],
    }


def process_security_event(
    db: Session,
    record: SecurityEvent,
):
    """
    Evaluate an already-flushed event against recent
    telemetry. Incident rows are added to the caller's
    transaction; this function does not commit.
    """

    now = record.received_at or datetime.utcnow()

    if now.tzinfo is None:
        now_aware = now.replace(tzinfo=timezone.utc)
    else:
        now_aware = now.astimezone(timezone.utc)

    history = _load_history(db, record, now)
    current = _event_dict(record)

    detections = []

    candidates = [
        detect_bruteforce(
            current,
            history,
            now=now_aware,
        ),
        detect_credential_stuffing(
            current,
            history,
            now=now_aware,
        ),
        detect_api_abuse(
            current,
            history,
            now=now_aware,
        ),
    ]

    payload_detection = _payload_indicator_detection(record)
    if payload_detection is not None:
        candidates.append(payload_detection)

    for result in candidates:
        if not result.get("detected"):
            continue

        incident_result = _create_incident(
            db,
            record,
            result,
            now,
        )

        detections.append(incident_result)

    return detections