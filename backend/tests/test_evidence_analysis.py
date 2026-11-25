from app.services.evidence_analysis import (
    aggregate_evidence,
    detect_source_conflicts,
)


def nutrient(source_id, amount, unit="g", basis_g=100, source="USDA"):
    return {
        "source_type": "nutrient",
        "source_id": source_id,
        "title": "Protein in Hummus",
        "content": f"Protein: {amount} {unit}",
        "rank_score": 0.02,
        "retrieval_sources": ["sql"],
        "source_ranks": {"sql": 1},
        "provenance": {
            "food_id": 10,
            "nutrient_key": "protein",
            "amount": amount,
            "unit": unit,
            "basis_g": basis_g,
            "source": source,
        },
    }


def test_aggregation_preserves_retrieval_channels_and_provenance():
    first = nutrient("10", 7, source="USDA")
    duplicate = {
        **nutrient("10", 7, source="USDA"),
        "retrieval_sources": ["vector", "graph"],
        "source_ranks": {"vector": 2, "graph": 1},
    }

    result = aggregate_evidence([first, duplicate])

    assert len(result) == 1
    assert set(result[0]["retrieval_sources"]) == {"sql", "vector", "graph"}
    assert result[0]["source_ranks"] == {
        "sql": 1,
        "vector": 2,
        "graph": 1,
    }
    assert result[0]["provenance"]["source"] == "USDA"
    assert result[0]["provenance"]["basis_g"] == 100


def test_comparable_different_values_are_reported_as_conflict():
    result = detect_source_conflicts([
        nutrient("10", 7, source="USDA"),
        nutrient("11", 9, source="Other source"),
    ])

    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["food_id"] == "10"
    assert result["conflicts"][0]["nutrient_key"] == "protein"
    assert len(result["conflicts"][0]["values"]) == 2


def test_close_values_within_tolerance_are_not_conflicts():
    result = detect_source_conflicts([
        nutrient("10", 7.00),
        nutrient("11", 7.01),
    ])

    assert result["conflicts"] == []


def test_different_units_are_incomparable_not_conflicting():
    result = detect_source_conflicts([
        nutrient("10", 7, unit="g"),
        nutrient("11", 7000, unit="mg"),
    ])

    assert result["conflicts"] == []
    assert len(result["incomparable"]) == 1


def test_different_measurement_bases_are_incomparable():
    result = detect_source_conflicts([
        nutrient("10", 7, basis_g=100),
        nutrient("11", 14, basis_g=200),
    ])

    assert result["conflicts"] == []
    assert len(result["incomparable"]) == 1


def test_invalid_measurement_is_reported():
    result = detect_source_conflicts([
        nutrient("10", None),
        nutrient("11", 7),
    ])

    assert len(result["invalid_evidence"]) == 1
    assert result["conflicts"] == []


def test_non_nutrient_evidence_is_ignored():
    result = detect_source_conflicts([
        {
            "source_type": "food",
            "source_id": "10",
            "provenance": {"food_id": 10},
        }
    ])

    assert result == {
        "conflicts": [],
        "incomparable": [],
        "invalid_evidence": [],
    }


def test_aggregation_does_not_merge_different_sources():
    result = aggregate_evidence([
        nutrient("10", 7),
        nutrient("11", 9),
    ])

    assert len(result) == 2
    assert {item["source_id"] for item in result} == {"10", "11"}
def test_aggregation_preserves_distinct_provenance_records():
    first = nutrient("10", 7, source="USDA")
    second = nutrient("10", 7, source="Secondary source")
    second["provenance"]["source_nutrient_id"] = "external-123"
    second["retrieval_sources"] = ["vector"]

    result = aggregate_evidence([first, second])

    assert len(result) == 1
    assert len(result[0]["provenance_records"]) == 2
    assert {
        record["source"] for record in result[0]["provenance_records"]
    } == {"USDA", "Secondary source"}
    assert result[0]["provenance"]["source"] == "USDA"
