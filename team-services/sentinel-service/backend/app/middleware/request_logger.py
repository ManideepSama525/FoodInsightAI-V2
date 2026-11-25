from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from app.database.database import SessionLocal
from app.models.incident import Incident

from app.services.detection_service import analyze_request

from app.ai.correlation_engine import correlate_incident
from app.ai.threat_scoring import calculate_threat_score
from app.ai.response_engine import generate_ai_response

from app.services.enforcement_service import (
    block_ip,
    is_ip_blocked,
)


class RequestLoggerMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):

        # -----------------------------------------
        # Ignore Sentinel XDR internal endpoints
        # -----------------------------------------

        ignored_prefixes = [
            # Sentinel XDR internal endpoints

            "/docs",
            "/openapi.json",
            "/redoc",
            "/health",
            "/login",
            "/incidents",
            "/integration",
            "/static",
            "/favicon.ico",

            "/dashboard",
            "/chart",
            "/campaigns",
            "/simulator",

            "/copilot",
            "/reports",
            "/timeline",
            "/mitre",
            "/analyst",
            "/campaign",
        ]

        path = request.url.path

        if any(
            path.startswith(prefix)
            for prefix in ignored_prefixes
        ):
            return await call_next(request)

        # -----------------------------------------
        # Source IP
        # -----------------------------------------

        source_ip = (
            request.client.host
            if request.client
            else "unknown"
        )

        # -----------------------------------------
        # Check Existing IP Block
        # -----------------------------------------

        if is_ip_blocked(source_ip):

            print("\n" + "=" * 70)
            print("ðŸš« SENTINEL XDR BLOCKED REQUEST")
            print("=" * 70)
            print(f"Source IP : {source_ip}")
            print(f"Target    : {path}")
            print("=" * 70 + "\n")

            return JSONResponse(
                status_code=403,
                content={
                    "blocked": True,
                    "message": "Request blocked by Sentinel XDR.",
                    "reason": "Source IP is currently blocked.",
                },
            )

        # -----------------------------------------
        # Read Request Body
        # -----------------------------------------

        body = b""

        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()

        # -----------------------------------------
        # Build Request Data
        # -----------------------------------------

        data = {
            "ip": source_ip,
            "method": request.method,
            "path": path,
            "query": request.url.query,
            "body": body.decode(errors="ignore"),
        }

        # -----------------------------------------
        # AI + Rule Detection
        # -----------------------------------------

        result = analyze_request(data)

        # -----------------------------------------
        # No Threat
        # -----------------------------------------

        if not result["detected"]:
            return await call_next(request)

        # -----------------------------------------
        # Threat Detected
        # -----------------------------------------

        db = SessionLocal()

        try:

            print("\n" + "=" * 70)
            print("ðŸš¨ SENTINEL XDR ALERT")
            print("=" * 70)

            print(
                f"Attack       : "
                f"{result.get('attack', 'Unknown')}"
            )

            print(
                f"Severity     : "
                f"{result.get('severity', 'Unknown')}"
            )

            print(
                f"Rule Conf.   : "
                f"{result.get('rule_confidence', result.get('confidence', 0))}%"
            )

            print(
                f"AI Prediction: "
                f"{result.get('ai_prediction', 'Unknown')}"
            )

            print(
                f"AI Confidence: "
                f"{result.get('ai_confidence', 0)}%"
            )

            print(
                f"Source IP    : {source_ip}"
            )

            print(
                f"Target       : {path}"
            )

            # ---------------------------------
            # Campaign Correlation
            # ---------------------------------

            campaign = correlate_incident(
                db=db,
                source_ip=source_ip,
                attack_type=result["attack"],
            )

            # ---------------------------------
            # Threat Score
            # ---------------------------------

            threat_score = calculate_threat_score(
                severity=result["severity"],
                ai_confidence=result.get(
                    "ai_confidence",
                    0,
                ),
                campaign=campaign["campaign"],
                frequency=campaign["incident_count"],
            )

            # ---------------------------------
            # Autonomous Response
            # ---------------------------------

            autonomous_response = generate_ai_response(
                attack_type=result["attack"],
                severity=result["severity"],

                # AI confidence
                confidence=result.get(
                    "ai_confidence",
                    0,
                ),

                # Rule confidence
                rule_confidence=result.get(
                    "rule_confidence",
                    result.get("confidence", 0),
                ),
            )

            # ---------------------------------
            # Incident Number
            # ---------------------------------

            total = (
                db.query(Incident).count()
                + 1
            )

            incident_number = (
                f"INC-{total:06d}"
            )

            # ---------------------------------
            # Create Incident
            # ---------------------------------

            incident = Incident(

                incident_id=incident_number,

                attack_type=result["attack"],

                severity=result["severity"],

                source_ip=source_ip,

                target=path,

                description=result.get(
                    "explanation",
                    "Threat detected.",
                ),

                ai_explanation=result.get(
                    "explanation",
                    "AI analysis unavailable.",
                ),

                confidence=result.get(
                    "confidence",
                    0,
                ),

                ai_prediction=result.get(
                    "ai_prediction"
                ),

                ai_confidence=result.get(
                    "ai_confidence"
                ),

                ai_model=(
                    "Logistic Regression + TF-IDF"
                ),

                threat_score=threat_score,

                response_action=(
                    autonomous_response["action"]
                ),

                status="Active",
            )

            # ---------------------------------
            # Save Incident
            # ---------------------------------

            db.add(incident)

            db.commit()

            db.refresh(incident)

            # ---------------------------------
            # Console Output
            # ---------------------------------

            print(
                f"Incident     : "
                f"{incident.incident_id}"
            )

            print(
                f"Threat Score : "
                f"{threat_score}/100"
            )

            print(
                f"Response     : "
                f"{autonomous_response['action']}"
            )

            print(
                f"Action Code  : "
                f"{autonomous_response.get('action_code', 'N/A')}"
            )

            print(
                f"Automation   : "
                f"{autonomous_response.get('automation', False)}"
            )

            # ---------------------------------
            # Enforcement
            # ---------------------------------

            action_code = autonomous_response.get(
                "action_code"
            )

            if (
                action_code == "BLOCK_IP"
                and autonomous_response.get(
                    "automation",
                    False,
                )
            ):

                # Global source-IP blocking disabled; this response blocks only the current request.

                print(
                    f"ðŸš« REQUEST BLOCKED (SOURCE IP NOT BLOCKED) : "
                    f"{source_ip}"
                )

                print("=" * 70 + "\n")

                return JSONResponse(
                    status_code=403,
                    content={
                        "blocked": True,

                        "message": (
                            "Request blocked by "
                            "Sentinel XDR."
                        ),

                        "incident_id": (
                            incident.incident_id
                        ),

                        "attack": result["attack"],

                        "severity": result["severity"],

                        "rule_confidence": result.get(
                            "rule_confidence",
                            result.get("confidence", 0),
                        ),

                        "ai_confidence": result.get(
                            "ai_confidence",
                            0,
                        ),

                        "threat_score": threat_score,

                        "action": (
                            autonomous_response["action"]
                        ),
                    },
                )

            print("=" * 70 + "\n")

            # ---------------------------------
            # Non-blocking Threat
            # ---------------------------------

            response = await call_next(request)

            return response

        except Exception as error:

            db.rollback()

            print(
                "âŒ Sentinel XDR incident "
                f"creation failed: {error}"
            )

            # Don't destroy the protected application
            # if Sentinel itself encounters an error.
            return await call_next(request)

        finally:

            db.close()
