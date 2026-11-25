def calculate_threat_score(

    severity: str,
    ai_confidence: float,
    campaign: bool,
    frequency: int,

):

    score = 0

    # ------------------------
    # Severity
    # ------------------------

    if severity == "Critical":
        score += 35

    elif severity == "High":
        score += 25

    elif severity == "Medium":
        score += 15

    else:
        score += 5

    # ------------------------
    # AI Confidence
    # ------------------------

    score += ai_confidence * 0.4

    # ------------------------
    # Campaign Bonus
    # ------------------------

    if campaign:
        score += 20

    # ------------------------
    # Frequency Bonus
    # ------------------------

    score += min(frequency, 10)

    return min(round(score), 100)