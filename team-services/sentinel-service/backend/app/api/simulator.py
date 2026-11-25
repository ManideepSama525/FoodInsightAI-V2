from fastapi import APIRouter

from app.database.database import SessionLocal
from app.models.incident import Incident

from app.services.detection_service import analyze_request

from app.ai.response_engine import generate_ai_response
from app.ai.threat_scoring import calculate_threat_score
from app.ai.correlation_engine import correlate_incident


router = APIRouter(
    prefix="/simulator",
    tags=["Attack Simulator"],
)


@router.post("/attack")
def simulate_attack(payload: dict):

    # ---------------------------------
    # Simulated HTTP Request
    # ---------------------------------

    request = {
        "ip": "192.168.100.55",
        "method": "POST",
        "path": payload.get("target", "/login"),
        "query": "",
        "body": payload.get("payload", ""),
    }

    # ---------------------------------
    # Rule + AI Detection
    # ---------------------------------

    result = analyze_request(request)

    if not result["detected"]:
        return {
            "success": False,
            "message": "No threat detected.",
            "ai_prediction": result.get("ai_prediction"),
            "ai_confidence": result.get("ai_confidence"),
        }

    db = SessionLocal()

    try:

        # ---------------------------------
        # Incident Number
        # ---------------------------------

        total = db.query(Incident).count() + 1

        # ---------------------------------
        # AI Campaign Correlation
        # ---------------------------------
        # The correlation engine checks
        # previous related incidents.

        previous_campaign = correlate_incident(
            db=db,
            source_ip=request["ip"],
            attack_type=result["attack"],
        )

        # ---------------------------------
        # Include Current Attack
        # ---------------------------------

        current_frequency = (
            previous_campaign.get("incident_count", 0) + 1
        )

        campaign_detected = (
            current_frequency >= 3
        )

        # ---------------------------------
        # AI Threat Score
        # ---------------------------------

        threat_score = calculate_threat_score(
            severity=result["severity"],
            ai_confidence=result.get("ai_confidence", 0),
            campaign=campaign_detected,
            frequency=current_frequency,
        )

        # ---------------------------------
        # AI Autonomous Response
        # ---------------------------------

        response = generate_ai_response(
            attack_type=result["attack"],
            severity=result["severity"],
            confidence=result.get("ai_confidence", 0),
        )

        # ---------------------------------
        # Save Incident
        # ---------------------------------

        incident = Incident(

            incident_id=f"INC-{total:06d}",

            attack_type=result["attack"],
            severity=result["severity"],

            source_ip=request["ip"],
            target=request["path"],

            description=result["explanation"],
            ai_explanation=result["explanation"],

            confidence=result["confidence"],

            # -----------------------------
            # AI Model
            # -----------------------------

            ai_prediction=result.get("ai_prediction"),
            ai_confidence=result.get("ai_confidence"),
            ai_model="Logistic Regression + TF-IDF",

            # -----------------------------
            # AI Threat Score
            # -----------------------------

            threat_score=threat_score,

            # -----------------------------
            # AI Response
            # -----------------------------

            response_action=response["action"],

            status="Active",
        )

        db.add(incident)
        db.commit()
        db.refresh(incident)

        # ---------------------------------
        # Campaign Information
        # ---------------------------------

        campaign = {
            "campaign": campaign_detected,
            "campaign_id": previous_campaign.get(
                "campaign_id"
            ),
            "incident_count": current_frequency,
            "risk": (
                "Critical"
                if campaign_detected
                else None
            ),
            "summary": (
                f"{current_frequency} coordinated "
                f"{result['attack']} attacks detected "
                f"from {request['ip']}."
                if campaign_detected
                else "No coordinated campaign detected."
            ),
        }

        # ---------------------------------
        # API Response
        # ---------------------------------

        return {

            "success": True,

            "message": "Threat detected successfully.",

            "incident": incident,

            "campaign": campaign,

            "threat_score": threat_score,

            "autonomous_response": response,

            "ai": {

                "prediction": result.get(
                    "ai_prediction"
                ),

                "confidence": result.get(
                    "ai_confidence"
                ),

                "scores": result.get(
                    "ai_scores"
                ),

                "model":
                    "Logistic Regression + TF-IDF",

            },

        }

    finally:

        db.close()