from app.detectors.sql_detector import detect_sql_injection
from app.detectors.xss_detector import detect_xss
from app.detectors.path_detector import detect_path_traversal
from app.detectors.command_detector import detect_command_injection

from app.ai.predict import predict_attack


def analyze_request(request):

    payload = (
        request.get("body", "")
        + " "
        + request.get("query", "")
        + " "
        + request.get("path", "")
    )

    # ----------------------------
    # AI Prediction
    # ----------------------------

    ai_result = predict_attack(payload)

    # ----------------------------
    # Rule-Based Detection
    # ----------------------------

    detectors = [
        detect_sql_injection,
        detect_xss,
        detect_path_traversal,
        detect_command_injection,
    ]

    for detector in detectors:

        result = detector(request)

        if result["detected"]:

            # --------------------------------
            # Preserve Rule Confidence
            # --------------------------------

            result["rule_confidence"] = result.get(
                "confidence",
                0,
            )

            # --------------------------------
            # Add AI Information
            # --------------------------------

            result["ai_prediction"] = (
                ai_result["prediction"]
            )

            result["ai_confidence"] = (
                ai_result["confidence"]
            )

            result["ai_scores"] = (
                ai_result["scores"]
            )

            return result

    # ----------------------------
    # If No Rule Matched
    # ----------------------------

    return {
        "detected": False,

        "rule_confidence": 0,

        "ai_prediction": (
            ai_result["prediction"]
        ),

        "ai_confidence": (
            ai_result["confidence"]
        ),

        "ai_scores": (
            ai_result["scores"]
        ),
    }