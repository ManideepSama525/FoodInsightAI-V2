from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.incident import Incident

router = APIRouter(
    prefix="/ai",
    tags=["AI Security Analyst"],
)


@router.get("/analyst/{incident_id}")
def analyst_summary(
    incident_id: str,
    db: Session = Depends(get_db)
):

    incident = (
        db.query(Incident)
        .filter(Incident.incident_id == incident_id)
        .first()
    )

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    attack = incident.attack_type

    summaries = {
        "SQL Injection": {
            "summary":
                "The AI model identified a SQL Injection attempt targeting the authentication endpoint. The payload attempts to manipulate SQL queries and may allow unauthorized access if input validation is insufficient.",
            "impact":
                "Possible database compromise, authentication bypass and data leakage.",
            "recommendations": [
                "Block the attacking IP address.",
                "Use parameterized SQL queries.",
                "Review authentication logs.",
                "Inspect database for unauthorized activity."
            ]
        },

        "Cross Site Scripting": {
            "summary":
                "The payload contains executable JavaScript designed to run in the victim's browser.",
            "impact":
                "Session hijacking, credential theft and client-side compromise.",
            "recommendations": [
                "Encode all output.",
                "Enable Content Security Policy.",
                "Sanitize user input.",
                "Review affected webpages."
            ]
        },

        "Directory Traversal": {
            "summary":
                "The request attempts to access restricted system files by traversing parent directories.",
            "impact":
                "Exposure of sensitive server files and configuration information.",
            "recommendations": [
                "Restrict filesystem access.",
                "Validate file paths.",
                "Disable directory listing.",
                "Review accessed files."
            ]
        },

        "Command Injection": {
            "summary":
                "The payload attempts to execute operating system commands through application input.",
            "impact":
                "Remote code execution and complete host compromise.",
            "recommendations": [
                "Isolate the affected host.",
                "Block malicious commands.",
                "Review server processes.",
                "Rotate credentials if necessary."
            ]
        }
    }

    info = summaries.get(
        attack,
        {
            "summary": "Unknown attack detected.",
            "impact": "Unknown.",
            "recommendations": []
        }
    )

    return {
        "incident_id": incident.incident_id,
        "prediction": incident.ai_prediction,
        "confidence": incident.ai_confidence,
        "model": incident.ai_model,
        "risk": incident.severity,
        "summary": info["summary"],
        "impact": info["impact"],
        "recommendations": info["recommendations"],
    }