from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.incident import Incident

router = APIRouter(
    prefix="/copilot",
    tags=["AI Copilot"],
)


@router.get("/latest")
def latest_incident(db: Session = Depends(get_db)):

    incident = (
        db.query(Incident)
        .order_by(Incident.id.desc())
        .first()
    )

    if incident is None:
        return {
            "message": "No incidents found."
        }

    return {
        "attack": incident.attack_type,
        "severity": incident.severity,
        "confidence": incident.confidence,
        "analysis": incident.ai_explanation,
        "recommendation": incident.response_action,
        "status": incident.status,
        "incident_id": incident.incident_id,
    }