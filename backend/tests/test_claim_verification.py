import pytest

from backend.app.services.claim_verification import verify_nutrient_claim


def claim(amount=8.5, unit="g", basis_g=100):
    return {
        "food_id": 5,
        "nutrient_key": "protein",
        "amount": amount,
        "unit": unit,
        "basis_g": basis_g,
    }


def evidence(amount=8.5, unit="g", basis_g=100, source="USDA"):
    provenance = {
        "food_id": 5,
        "nutrient_key": "protein",
        "amount": amount,
        "unit": unit,
        "basis_g": basis_g,
        "source": source,
    }
    return {
        "source_type": "nutrient",
        "source_id": "5:protein",
        "provenance": provenance,
        "provenance_records": [provenance],
    }


def test_matching_claim_is_supported():
    result = verify_nutrient_claim(claim(), [evidence()])
    assert result["status"] == "supported"


def test_contradictory_claim_is_conflicting():
    result = verify_nutrient_claim(
        claim(amount=15), [evidence(amount=8.5)]
    )
    assert result["status"] == "conflicting"


def test_disagreeing_sources_are_conflicting():
    first = evidence(amount=8.5)
    second = evidence(amount=12, source="Secondary source")

    result = verify_nutrient_claim(
        claim(),
        [{
            **first,
            "provenance_records": [
                first["provenance"],
                second["provenance"],
            ],
        }],
    )

    assert result["status"] == "conflicting"
    assert len(result["supporting_evidence"]) == 2


def test_different_measurement_basis_is_incomparable():
    result = verify_nutrient_claim(
        claim(), [evidence(amount=17, basis_g=200)]
    )
    assert result["status"] == "incomparable"


def test_different_units_are_incomparable():
    result = verify_nutrient_claim(
        claim(), [evidence(amount=8500, unit="mg")]
    )
    assert result["status"] == "incomparable"


def test_missing_evidence_is_insufficient():
    result = verify_nutrient_claim(claim(), [])
    assert result["status"] == "insufficient_evidence"


def test_unrelated_food_evidence_is_ignored():
    item = evidence()
    item["provenance"]["food_id"] = 99
    item["provenance_records"] = [item["provenance"]]

    result = verify_nutrient_claim(claim(), [item])
    assert result["status"] == "insufficient_evidence"


@pytest.mark.parametrize("invalid_claim", [
    {},
    {"food_id": 5, "nutrient_key": "protein"},
    {
        "food_id": 5,
        "nutrient_key": "protein",
        "amount": "invalid",
        "unit": "g",
        "basis_g": 100,
    },
    {
        "food_id": 5,
        "nutrient_key": "protein",
        "amount": 8.5,
        "unit": "g",
        "basis_g": 0,
    },
])
def test_invalid_claim_is_rejected(invalid_claim):
    with pytest.raises(ValueError):
        verify_nutrient_claim(invalid_claim, [])

def test_missing_source_attribution_cannot_support_claim():
    item = evidence()
    item["provenance"].pop("source")
    item["provenance_records"] = [item["provenance"]]

    result = verify_nutrient_claim(claim(), [item])

    assert result["status"] == "incomparable"
    assert result["supporting_evidence"] == []
    assert len(result["incomparable_evidence"]) == 1
    assert result["incomparable_evidence"][0]["source"] is None

@pytest.mark.parametrize(
    "source",
    [None, "", "   ", 123],
)
def test_invalid_source_attribution_cannot_support_claim(source):
    item = evidence()
    item["provenance"]["source"] = source
    item["provenance_records"] = [item["provenance"]]

    result = verify_nutrient_claim(claim(), [item])

    assert result["status"] == "incomparable"
    assert result["supporting_evidence"] == []
    assert len(result["incomparable_evidence"]) == 1    
