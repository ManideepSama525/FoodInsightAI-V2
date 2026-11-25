import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal


ModelSource = Literal["food101", "indian"]


@dataclass(frozen=True)
class AnalysisRoutingDecision:
    status: str
    model_source: str
    food_label: str | None
    freshness: str
    nutrition: str
    recipe: str
    fraud: str
    requires_review: bool
    reasons: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_compatibility_config() -> dict:
    """Load and validate the food-analysis compatibility configuration."""
    config_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "food_analysis_compatibility.json"
    )

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Food analysis compatibility configuration not found: {config_path}"
        )

    with config_path.open("r", encoding="utf-8-sig") as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise ValueError("Compatibility configuration must be a JSON object.")

    entries = config.get("recognition_classes")
    categories = config.get("freshness_categories")

    if not isinstance(entries, list) or not isinstance(categories, list):
        raise ValueError("Compatibility configuration has invalid collection fields.")

    if len(entries) != 116 or len(categories) != 24:
        raise ValueError(
            "Compatibility configuration must contain 116 recognition classes "
            "and 24 freshness categories."
        )

    class_map = {}

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid recognition class entry.")

        source = entry.get("model_source")
        label = entry.get("class_label")

        if source not in ("food101", "indian") or not isinstance(label, str):
            raise ValueError("Invalid model source or class label in configuration.")

        key = (source, label.strip().lower())

        if not key[1] or key in class_map:
            raise ValueError(f"Empty or duplicate recognition class: {key}")

        if (
            entry.get("freshness") != "NOT_VALIDATED"
            or entry.get("fraud") != "NOT_VALIDATED"
            or entry.get("nutrition") != "LOOKUP_ONLY"
            or entry.get("recipe") != "LOOKUP_ONLY"
        ):
            raise ValueError(f"Unexpected compatibility status for {key}")

        class_map[key] = entry

    if (
        sum(source == "food101" for source, _ in class_map) != 101
        or sum(source == "indian" for source, _ in class_map) != 15
    ):
        raise ValueError("Recognition class distribution is invalid.")

    if not all(isinstance(category, str) and category for category in categories):
        raise ValueError("Freshness categories contain invalid values.")

    if len(set(categories)) != 24:
        raise ValueError("Freshness categories contain duplicates.")

    return {
        "class_map": class_map,
        "freshness_categories": tuple(categories),
    }


def route_food_analysis(
    model_source: ModelSource,
    predicted_food: str | None,
    confidence: float | None,
    needs_review: bool,
) -> AnalysisRoutingDecision:
    """
    Route recognized food to downstream analysis conservatively.

    Recognition classes are not automatically treated as compatible with
    the independently trained Freshness V1 or food-fraud models.
    """

    if model_source not in ("food101", "indian"):
        raise ValueError("model_source must be 'food101' or 'indian'")

    if confidence is not None:
        if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    if needs_review or not predicted_food or confidence is None:
        return AnalysisRoutingDecision(
            status="REVIEW_REQUIRED",
            model_source=model_source,
            food_label=predicted_food,
            freshness="NOT_RUN",
            nutrition="NOT_RUN",
            recipe="NOT_RUN",
            fraud="NOT_RUN",
            requires_review=True,
            reasons=(
                "Food recognition is inconclusive; downstream analysis is withheld.",
            ),
        )

    if not isinstance(predicted_food, str):
        raise ValueError("predicted_food must be a string or None")

    label = predicted_food.strip().lower()

    if not label:
        return AnalysisRoutingDecision(
            status="REVIEW_REQUIRED",
            model_source=model_source,
            food_label=None,
            freshness="NOT_RUN",
            nutrition="NOT_RUN",
            recipe="NOT_RUN",
            fraud="NOT_RUN",
            requires_review=True,
            reasons=("The recognized food label is empty.",),
        )

    config = _load_compatibility_config()

    if (model_source, label) not in config["class_map"]:
        raise ValueError(
            f"Unrecognized class '{label}' for model source '{model_source}'."
        )

    return AnalysisRoutingDecision(
        status="PARTIAL",
        model_source=model_source,
        food_label=label,
        freshness="UNSUPPORTED",
        nutrition="LOOKUP_CANDIDATE",
        recipe="LOOKUP_CANDIDATE",
        fraud="NOT_VALIDATED",
        requires_review=False,
        reasons=(
            "Direct Freshness V1 inference has not been validated for this recognition class.",
            "Nutrition lookup may be attempted; database coverage and result availability are not guaranteed.",
            "Recipe lookup may be attempted; database coverage and result availability are not guaranteed.",
            "No food-fraud detection model has been validated for this recognition class.",
        ),
    )
