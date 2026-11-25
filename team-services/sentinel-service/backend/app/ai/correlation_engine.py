from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.incident import Incident


def correlate_incident(
    db: Session,
    source_ip: str,
    attack_type: str,
):

    five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)

    incidents = (
        db.query(Incident)
        .filter(
            Incident.source_ip == source_ip,
            Incident.attack_type == attack_type,
            Incident.created_at >= five_minutes_ago,
        )
        .all()
    )

    count = len(incidents)

    if count >= 5:

        return {
            "campaign": True,
            "campaign_id": f"CMP-{source_ip.replace('.', '')}",
            "incident_count": count,
            "risk": "Critical",
            "summary": (
                f"{count} {attack_type} attacks "
                f"detected from {source_ip} "
                "within five minutes."
            ),
        }

    return {
        "campaign": False,
        "incident_count": count,
    }