from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.incident import Incident


router = APIRouter(
    prefix="/chart",
    tags=["Charts"],
)


@router.get("/attacks")
def attack_chart(
    db: Session = Depends(get_db),
):

    incidents = db.query(Incident).all()

    # ------------------------------------------------
    # Group attack statistics
    # ------------------------------------------------

    grouped = defaultdict(list)

    for incident in incidents:

        grouped[incident.attack_type].append(
            incident
        )

    # ------------------------------------------------
    # Build chart data
    # ------------------------------------------------

    data = []

    for attack, attack_incidents in grouped.items():

        count = len(attack_incidents)

        # Only use threat scores that exist
        threat_scores = [
            incident.threat_score
            for incident in attack_incidents
            if incident.threat_score is not None
        ]

        average_threat_score = (
            sum(threat_scores) / len(threat_scores)
            if threat_scores
            else 0
        )

        data.append(
            {
                "attack": attack,
                "count": count,
                "average_threat_score": round(
                    average_threat_score,
                    1,
                ),
            }
        )

    return data