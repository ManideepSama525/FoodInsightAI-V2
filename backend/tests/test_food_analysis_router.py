import json
from pathlib import Path

import pytest

from backend.app.services.food_analysis_router import (
    _load_compatibility_config,
    route_food_analysis,
)


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ("food101", "pizza"),
        ("indian", "biryani"),
    ],
)
def test_accepted_recognition_routes_conservatively(source, label):
    result = route_food_analysis(
        model_source=source,
        predicted_food=label,
        confidence=0.94,
        needs_review=False,
    )

    assert result.status == "PARTIAL"
    assert result.freshness == "UNSUPPORTED"
    assert result.nutrition == "LOOKUP_CANDIDATE"
    assert result.recipe == "LOOKUP_CANDIDATE"
    assert result.fraud == "NOT_VALIDATED"
    assert result.requires_review is False


def test_label_is_normalized_before_lookup():
    result = route_food_analysis(
        model_source="food101",
        predicted_food="  PIZZA  ",
        confidence=0.94,
        needs_review=False,
    )

    assert result.food_label == "pizza"


def test_low_confidence_prediction_requires_review():
    result = route_food_analysis(
        model_source="indian",
        predicted_food=None,
        confidence=0.42,
        needs_review=True,
    )

    assert result.status == "REVIEW_REQUIRED"
    assert result.freshness == "NOT_RUN"
    assert result.nutrition == "NOT_RUN"
    assert result.recipe == "NOT_RUN"
    assert result.fraud == "NOT_RUN"
    assert result.requires_review is True


def test_missing_prediction_requires_review():
    result = route_food_analysis(
        model_source="food101",
        predicted_food=None,
        confidence=None,
        needs_review=False,
    )

    assert result.status == "REVIEW_REQUIRED"
    assert result.requires_review is True


def test_empty_prediction_requires_review():
    result = route_food_analysis(
        model_source="food101",
        predicted_food="   ",
        confidence=0.9,
        needs_review=False,
    )

    assert result.status == "REVIEW_REQUIRED"
    assert result.requires_review is True


def test_unknown_class_is_rejected():
    with pytest.raises(ValueError, match="Unrecognized class"):
        route_food_analysis(
            model_source="food101",
            predicted_food="unknown_food",
            confidence=0.95,
            needs_review=False,
        )


def test_wrong_model_class_combination_is_rejected():
    with pytest.raises(ValueError, match="Unrecognized class"):
        route_food_analysis(
            model_source="indian",
            predicted_food="pizza",
            confidence=0.95,
            needs_review=False,
        )


def test_invalid_model_source_is_rejected():
    with pytest.raises(ValueError, match="model_source"):
        route_food_analysis(
            model_source="unknown",
            predicted_food="pizza",
            confidence=0.95,
            needs_review=False,
        )


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_confidence_is_rejected(confidence):
    with pytest.raises(ValueError, match="confidence"):
        route_food_analysis(
            model_source="food101",
            predicted_food="pizza",
            confidence=confidence,
            needs_review=False,
        )


def test_compatibility_configuration_has_expected_counts():
    config = _load_compatibility_config()

    assert len(config["class_map"]) == 116
    assert sum(
        source == "food101" for source, _ in config["class_map"]
    ) == 101
    assert sum(
        source == "indian" for source, _ in config["class_map"]
    ) == 15
    assert len(config["freshness_categories"]) == 24


def test_configuration_matches_model_label_files():
    root = Path(__file__).resolve().parents[2]

    with (root / "artifacts" / "classes.json").open(
        encoding="utf-8-sig"
    ) as file:
        food101 = set(json.load(file))

    with (root / "artifacts" / "indian_food_v1" / "classes.json").open(
        encoding="utf-8-sig"
    ) as file:
        indian = set(json.load(file))

    config = _load_compatibility_config()
    class_map = config["class_map"]

    assert {
        label for source, label in class_map if source == "food101"
    } == food101

    assert {
        label for source, label in class_map if source == "indian"
    } == indian
