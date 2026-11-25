from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.incident import Incident

router = APIRouter(
    prefix="/campaigns",
    tags=["AI Campaign Correlation"],
)


@router.get("/")
def get_campaigns(db: Session = Depends(get_db)):

    incidents = (
        db.query(Incident)
        .order_by(Incident.created_at.desc())
        .all()
    )

    campaigns = defaultdict(list)

    for incident in incidents:

        key = (
            incident.source_ip,
            incident.attack_type,
        )

        campaigns[key].append(incident)

    response = []

    campaign_number = 1

    for key, items in campaigns.items():

        if len(items) < 3:
            continue

        response.append({

            "campaign_id":
                f"CMP-{campaign_number:06d}",

            "attack_type":
                key[1],

            "source_ip":
                key[0],

            "incident_count":
                len(items),

            "severity":
                items[0].severity,

            "latest_incident":
                items[0].incident_id,

            "status":
                "Active",

            "summary":
                f"{len(items)} coordinated "
                f"{key[1]} attacks detected "
                f"from {key[0]}.",

        })

        campaign_number += 1

    return response