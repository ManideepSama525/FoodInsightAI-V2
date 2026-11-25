from backend.app.services.claim_verification import verify_nutrient_claim


def make_claim(amount):
    return {
        "food_id": 1,
        "nutrient_key": "protein",
        "amount": amount,
        "unit": "g",
        "basis_g": 100,
    }


def make_evidence(amount, source="USDA", source_id="1:protein"):
    provenance = {
        "food_id": 1,
        "nutrient_key": "protein",
        "amount": str(amount),
        "unit": "g",
        "basis_g": "100",
        "source": source,
        "source_nutrient_id": "1003",
    }
    return {
        "source_type": "nutrient",
        "source_id": source_id,
        "provenance": provenance,
        "provenance_records": [provenance],
    }


def test_same_measurement_from_multiple_channels_is_deduplicated():
    first = make_evidence("7.35000")
    second = make_evidence("7.35")
    second["provenance"] = {
        **second["provenance"],
        "basis_g": "100.0",
    }
    second["provenance_records"] = [second["provenance"]]

    result = verify_nutrient_claim(
        make_claim(7.35),
        [first, second],
    )

    assert result["status"] == "supported"
    assert len(result["supporting_evidence"]) == 1


def test_independent_sources_are_preserved():
    first = make_evidence("8.5", source="USDA")
    second = make_evidence("8.5", source="Independent source")

    result = verify_nutrient_claim(
        make_claim(8.5),
        [first, second],
    )

    assert result["status"] == "supported"
    assert len(result["supporting_evidence"]) == 2


def test_different_values_are_not_deduplicated():
    first = make_evidence("8.5")
    second = make_evidence("12")

    first["provenance_records"] = [
        first["provenance"],
        second["provenance"],
    ]

    result = verify_nutrient_claim(
        make_claim(8.5),
        [first],
    )

    assert result["status"] == "conflicting"
    assert len(result["supporting_evidence"]) == 2


def test_different_source_nutrient_ids_are_preserved():
    first = make_evidence("8.5")
    second = make_evidence("8.5")
    second["provenance"]["source_nutrient_id"] = "9999"
    second["provenance_records"] = [second["provenance"]]

    result = verify_nutrient_claim(
        make_claim(8.5),
        [first, second],
    )

    assert result["status"] == "supported"
    assert len(result["supporting_evidence"]) == 2
