from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.incident import Incident

router = APIRouter(
    prefix="/timeline",
    tags=["Timeline"],
)


@router.get("/{incident_id}")
def incident_timeline(
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
        return []

    return [

        {
            "time": incident.created_at.strftime("%H:%M:%S"),
            "event": "Threat Detected",
        },

        {
            "time": incident.created_at.strftime("%H:%M:%S"),
            "event": "AI Analysis Completed",
        },

        {
            "time": incident.created_at.strftime("%H:%M:%S"),
            "event": "Incident Created",
        },

        {
            "time": incident.created_at.strftime("%H:%M:%S"),
            "event": "SOC Notification Sent",
        },

        {
            "time": incident.created_at.strftime("%H:%M:%S"),
            "event": "Response Pending",
        },

    ]