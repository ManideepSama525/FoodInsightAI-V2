from app.services.evidence_analysis import assess_provenance_quality


def nutrient_record(**overrides):
    record = {
        "food_id": 10,
        "nutrient_key": "protein",
        "amount": "7.35",
        "unit": "g",
        "basis_g": "100",
        "source": "usda_foundation",
    }
    record.update(overrides)
    return record


def test_complete_nutrient_provenance_is_complete():
    result = assess_provenance_quality({
        "source_type": "nutrient",
        "provenance": nutrient_record(),
    })

    assert result["status"] == "complete"
    assert result["issues"] == []


def test_missing_derivation_metadata_is_optional_not_invalid():
    result = assess_provenance_quality({
        "source_type": "nutrient",
        "provenance": nutrient_record(),
    })

    assert result["status"] == "complete"
    assert result["optional_metadata_unavailable"]


def test_missing_source_attribution_is_partial():
    record = nutrient_record()
    record.pop("source")

    result = assess_provenance_quality({
        "source_type": "nutrient",
        "provenance": record,
    })

    assert result["status"] == "partial"
    assert any("source" in issue for issue in result["issues"])


def test_invalid_nutrient_amount_is_invalid():
    result = assess_provenance_quality({
        "source_type": "nutrient",
        "provenance": nutrient_record(amount="-"),
    })

    assert result["status"] == "invalid"


def test_missing_measurement_basis_is_invalid():
    result = assess_provenance_quality({
        "source_type": "nutrient",
        "provenance": nutrient_record(basis_g=None),
    })

    assert result["status"] == "invalid"


def test_food_provenance_requires_attribution_and_identifier():
    result = assess_provenance_quality({
        "source_type": "food",
        "provenance": {
            "source": "usda_foundation",
            "external_id": "12345",
        },
    })

    assert result["status"] == "complete"


def test_empty_provenance_is_partial():
    result = assess_provenance_quality({
        "source_type": "nutrient",
        "provenance": {},
    })

    assert result["status"] == "invalid"
    assert result["records_assessed"] == 1


def test_multiple_provenance_records_are_assessed():
    result = assess_provenance_quality({
        "source_type": "nutrient",
        "provenance_records": [
            nutrient_record(),
            nutrient_record(source=None),
        ],
    })

    assert result["records_assessed"] == 2
    assert result["status"] == "partial"
