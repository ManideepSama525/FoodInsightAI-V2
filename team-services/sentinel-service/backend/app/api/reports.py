import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.incident import Incident

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


@router.get("/csv")
def export_csv(db: Session = Depends(get_db)):

    incidents = db.query(Incident).all()

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Incident ID",
        "Attack",
        "Severity",
        "Source IP",
        "Target",
        "Confidence",
        "Status",
    ])

    for incident in incidents:
        writer.writerow([
            incident.incident_id,
            incident.attack_type,
            incident.severity,
            incident.source_ip,
            incident.target,
            incident.confidence,
            incident.status,
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=sentinel_report.csv"
        },
    )