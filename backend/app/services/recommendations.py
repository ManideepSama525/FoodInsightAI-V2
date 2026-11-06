from typing import Any

from backend.app.services.food_safety import assess_ingredients


GOAL_METRICS = {
    "high protein": {"protein": 1},
    "high fiber": {"fiber": 1},
    "low calorie": {"energy_kcal": -1},
    "weight management": {
        "protein": 1,
        "fiber": 1,
        "energy_kcal": -1,
    },
    "muscle building": {"protein": 1},
    "balanced nutrition": {
        "protein": 1,
        "fiber": 1,
        "total_sugars": -1,
        "sodium": -1,
    },
    "low sugar": {"total_sugars": -1},
}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not result == result or abs(result) == float("inf"):
        return None
    return result


def _food_values(food) -> dict[str, float]:
    values: dict[str, float] = {}
    for nutrient in food.nutrients:
        amount = _number(nutrient.amount)
        basis = _number(nutrient.basis_g)
        if amount is None or basis is None or basis <= 0:
            continue
        values[nutrient.nutrient_key] = amount * 100 / basis
    return values


def recommend_foods(foods: list, profile, limit: int = 10) -> dict:
    if not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")

    profile_goals = profile.goals if profile and profile.goals else []
    goals = sorted({
        goal.strip().casefold()
        for goal in profile_goals
        if isinstance(goal, str)
        and goal.strip().casefold() in GOAL_METRICS
    })
    if not goals:
        goals = ["balanced nutrition"]

    metrics: dict[str, int] = {}
    for goal in goals:
        metrics.update(GOAL_METRICS[goal])

    candidates = []
    excluded_count = 0

    for food in foods:
        values = _food_values(food)

        # A catalog food name is not a complete ingredient list. Use a
        # lower confidence so any name-based match remains explicitly possible.
        safety = assess_ingredients(
            [{"name": food.name, "confidence": 0.5}],
            profile,
        )
        if safety.status in {"allergy_conflict", "preference_conflict"}:
            excluded_count += 1
            continue

        candidates.append({
            "food": food,
            "values": values,
            "safety_status": safety.status,
        })

    for metric, direction in metrics.items():
        available = [
            item for item in candidates
            if metric in item["values"]
        ]
        # One record cannot be meaningfully ranked against alternatives.
        if len(available) < 2:
            continue

        ordered = sorted(
            available,
            key=lambda item: item["values"][metric],
            reverse=(direction > 0),
        )
        count = len(ordered)
        for index, item in enumerate(ordered):
            percentile = 1 - index / (count - 1)
            item.setdefault("metric_scores", {})[metric] = percentile

    scored = []
    for item in candidates:
        metric_scores = item.get("metric_scores", {})
        if not metric_scores:
            continue

        score = sum(metric_scores.values()) / len(metric_scores)
        reasons = [
            f"Ranks relatively well for {metric.replace('_', ' ')}"
            for metric, percentile in metric_scores.items()
            if percentile >= 0.7
        ]
        if not reasons:
            reasons = ["Compared using available nutrient data for your goals"]

        food = item["food"]
        scored.append({
            "food_id": food.id,
            "name": food.name,
            "category": food.category,
            "source": food.source,
            "score": round(score * 100, 1),
            "reasons": reasons,
            "nutrients_per_100g": [
                {
                    "key": nutrient.nutrient_key,
                    "name": nutrient.display_name,
                    "amount_per_100g": item["values"].get(nutrient.nutrient_key),
                    "unit": nutrient.unit,
                    "source": nutrient.source,
                }
                for nutrient in food.nutrients
            ],
            "safety_screen": item["safety_status"],
            "safety_note": (
                "Only the catalog food name was screened at possible-match "
                "confidence. This is not a complete ingredient list and does "
                "not establish allergen or dietary safety."
            ),
        })

    scored.sort(key=lambda item: (-item["score"], item["name"].casefold()))

    return {
        "goals_used": goals,
        "recommendations": scored[:limit],
        "excluded_known_conflicts": excluded_count,
        "method": "Relative nutrient ranking among available local catalog foods.",
        "limitations": [
            "Nutrient values are compared per 100 g where available.",
            "Missing nutrient values are not treated as zero.",
            "At least two comparable catalog records are required to rank a nutrient.",
            "Scores are relative to the current catalog, not clinical assessments.",
            "Food names do not provide complete ingredient or cross-contact information.",
            "Recommendations do not guarantee allergen or dietary safety.",
        ],
    }