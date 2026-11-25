from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.database import get_db
from app.models.incident import Incident


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


@router.get("/stats")
def dashboard_stats(
    db: Session = Depends(get_db),
):

    # --------------------------------
    # Incident Statistics
    # --------------------------------

    total = db.query(Incident).count()

    active = (
        db.query(Incident)
        .filter(Incident.status == "Active")
        .count()
    )

    critical = (
        db.query(Incident)
        .filter(Incident.severity == "Critical")
        .count()
    )

    average_confidence = db.query(
        func.avg(Incident.confidence)
    ).scalar()

    # --------------------------------
    # AI Campaign Count
    # --------------------------------

    grouped = {}

    incidents = db.query(Incident).all()

    for incident in incidents:

        key = (
            incident.source_ip,
            incident.attack_type,
        )

        grouped[key] = grouped.get(key, 0) + 1

    campaign_count = sum(
        1
        for count in grouped.values()
        if count >= 3
    )

    # --------------------------------
    # AI Threat Score Statistics
    # --------------------------------

    average_threat_score = db.query(
        func.avg(Incident.threat_score)
    ).scalar()

    highest_threat_score = db.query(
        func.max(Incident.threat_score)
    ).scalar()

    # --------------------------------
    # High Risk Incidents
    # --------------------------------
    # Threat Score >= 60

    high_risk_incidents = (
        db.query(Incident)
        .filter(
            Incident.threat_score >= 60
        )
        .count()
    )

    # --------------------------------
    # AI Detection Rate
    # --------------------------------

    ai_detected = (
        db.query(Incident)
        .filter(
            Incident.ai_prediction.isnot(None)
        )
        .count()
    )

    if total > 0:
        ai_detection_rate = (
            ai_detected / total
        ) * 100
    else:
        ai_detection_rate = 0

    # --------------------------------
    # Response
    # --------------------------------

    return {

        # Existing statistics
        "total": total,

        "active": active,

        "critical": critical,

        "campaigns": campaign_count,

        "average_confidence": round(
            average_confidence or 0,
            1,
        ),

        # New AI Risk statistics
        "average_threat_score": round(
            average_threat_score or 0,
            1,
        ),

        "highest_threat_score": round(
            highest_threat_score or 0,
            1,
        ),

        "high_risk_incidents": high_risk_incidents,

        "ai_detection_rate": round(
            ai_detection_rate,
            1,
        ),
    }