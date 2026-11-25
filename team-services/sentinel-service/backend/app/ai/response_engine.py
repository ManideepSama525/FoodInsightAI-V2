def generate_ai_response(
    attack_type: str,
    severity: str,
    confidence: float,
    rule_confidence: float = 0,
):

    confidence = float(confidence)
    rule_confidence = float(rule_confidence)

    # ------------------------------------
    # Critical
    # ------------------------------------

    if severity == "Critical":

        # Strong deterministic rule detection
        if rule_confidence >= 95:

            return {
                "action": "🚨 Block Source IP Immediately",
                "action_code": "BLOCK_IP",
                "priority": "P1",
                "automation": True,
                "reason": (
                    "Critical attack with extremely "
                    "high rule confidence."
                ),
            }

        # Strong combined evidence
        if (
            rule_confidence >= 80
            or confidence >= 80
        ):

            return {
                "action": "⚠️ Quarantine Endpoint",
                "action_code": "QUARANTINE_ENDPOINT",
                "priority": "P1",
                "automation": True,
                "reason": (
                    "Critical attack with strong "
                    "detection confidence."
                ),
            }

        return {
            "action": "👨‍💻 SOC Manual Investigation",
            "action_code": "MANUAL_INVESTIGATION",
            "priority": "P2",
            "automation": False,
            "reason": (
                "Evidence below automation threshold."
            ),
        }

    # ------------------------------------
    # High
    # ------------------------------------

    if severity == "High":

        if (
            rule_confidence >= 90
            or confidence >= 90
        ):

            return {
                "action": "🔒 Block Session",
                "action_code": "BLOCK_SESSION",
                "priority": "P2",
                "automation": True,
                "reason": (
                    "High confidence malicious activity."
                ),
            }

        return {
            "action": "🕵 Monitor Activity",
            "action_code": "MONITOR",
            "priority": "P3",
            "automation": False,
            "reason": (
                "Requires analyst verification."
            ),
        }

    # ------------------------------------
    # Medium
    # ------------------------------------

    if severity == "Medium":

        return {
            "action": "📋 Generate Alert",
            "action_code": "ALERT",
            "priority": "P3",
            "automation": False,
            "reason": "Medium severity event.",
        }

    # ------------------------------------
    # Low
    # ------------------------------------

    return {
        "action": "📝 Log Only",
        "action_code": "LOG_ONLY",
        "priority": "P4",
        "automation": False,
        "reason": "Low risk activity.",
    }