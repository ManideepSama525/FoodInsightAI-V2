from app.database.database import SessionLocal
from app.models.incident import Incident


def seed_demo_data():
    db = SessionLocal()

    if db.query(Incident).count() > 0:
        db.close()
        return {"message": "Database already contains data."}

    demo = [
        Incident(
            incident_id="INC-000001",
            attack_type="SQL Injection",
            severity="Critical",
            source_ip="192.168.1.10",
            target="/login",
            description="SQL keywords detected in login request.",
            ai_explanation="Detected UNION SELECT pattern.",
            confidence=98.7,
            response_action="Block IP",
            status="Active",
        ),
        Incident(
            incident_id="INC-000002",
            attack_type="Cross Site Scripting",
            severity="High",
            source_ip="192.168.1.22",
            target="/search",
            description="JavaScript payload detected.",
            ai_explanation="Possible reflected XSS attack.",
            confidence=94.2,
            response_action="Sanitize Input",
            status="Investigating",
        ),
        Incident(
            incident_id="INC-000003",
            attack_type="Brute Force",
            severity="Medium",
            source_ip="10.0.0.45",
            target="/admin",
            description="Multiple failed login attempts.",
            ai_explanation="Login threshold exceeded.",
            confidence=91.4,
            response_action="Rate Limit",
            status="Resolved",
        ),
    ]

    db.add_all(demo)
    db.commit()
    db.close()

    return {"message": "Demo incidents added successfully."}