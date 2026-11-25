from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.incident import Incident
from app.schemas.incident import IncidentCreate
from app.schemas.status import StatusUpdate


router = APIRouter(
    prefix="/incidents",
    tags=["Incidents"],
)


# ---------------------------------------------------------
# Create Incident
# ---------------------------------------------------------

@router.post("/")
def create_incident(
    incident: IncidentCreate,
    db: Session = Depends(get_db),
):

    total = db.query(Incident).count() + 1

    incident_number = f"INC-{total:06d}"

    new_incident = Incident(
        incident_id=incident_number,
        attack_type=incident.attack_type,
        severity=incident.severity,
        source_ip=incident.source_ip,
        target=incident.target,
        description=incident.description,
        ai_explanation=incident.ai_explanation,
        confidence=incident.confidence,
        response_action=incident.response_action,
        created_at=datetime.utcnow(),
        status="Active",
        acknowledged=False,
    )

    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    return new_incident


# ---------------------------------------------------------
# Get All Incidents
# ---------------------------------------------------------

@router.get("/")
def get_incidents(
    db: Session = Depends(get_db),
):
    return db.query(Incident).all()


# ---------------------------------------------------------
# Get Single Incident
# ---------------------------------------------------------

@router.get("/{incident_id}")
def get_incident(
    incident_id: str,
    db: Session = Depends(get_db),
):

    incident = (
        db.query(Incident)
        .filter(
            Incident.incident_id == incident_id
        )
        .first()
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return incident


# ---------------------------------------------------------
# Update Incident Status
# ---------------------------------------------------------

@router.patch("/{incident_id}/status")
def update_incident_status(
    incident_id: str,
    update: StatusUpdate,
    db: Session = Depends(get_db),
):

    incident = (
        db.query(Incident)
        .filter(
            Incident.incident_id == incident_id
        )
        .first()
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    incident.status = update.status

    db.commit()
    db.refresh(incident)

    return {
        "message": "Status Updated Successfully",
        "incident": incident,
    }


# ---------------------------------------------------------
# Acknowledge Security Alert
# ---------------------------------------------------------

@router.patch("/{incident_id}/acknowledge")
def acknowledge_incident(
    incident_id: str,
    db: Session = Depends(get_db),
):

    incident = (
        db.query(Incident)
        .filter(
            Incident.incident_id == incident_id
        )
        .first()
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    incident.acknowledged = True

    db.commit()
    db.refresh(incident)

    return {
        "message": "Security alert acknowledged.",
        "incident_id": incident.incident_id,
        "acknowledged": incident.acknowledged,
    }