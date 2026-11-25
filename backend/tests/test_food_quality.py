from decimal import Decimal
from types import SimpleNamespace

from backend.app.services.food_quality import assess_food_quality


def make_nutrient(
    key="protein",
    amount="7.5",
    basis="100",
    unit="g",
    source="test_source",
):
    return SimpleNamespace(
        nutrient_key=key,
        display_name=key.title(),
        amount=Decimal(amount) if amount is not None else None,
        unit=unit,
        basis_g=Decimal(basis) if basis is not None else None,
        source=source,
        source_nutrient_id="source-1",
        derivation_code=None,
        derivation_description=None,
        derivation_source_description=None,
    )


def make_food(nutrients=None):
    return SimpleNamespace(
        id=10,
        name="Test food",
        source="test_catalog",
        external_id="food-10",
        source_url=None,
        nutrients=nutrients or [],
    )


def make_document(
    *,
    food_id=10,
    source_id="external:protein",
    amount="9.0",
    status="indexed",
):
    return SimpleNamespace(
        source_type="nutrient",
        source_id=source_id,
        title="External protein evidence",
        content="Test evidence",
        status=status,
        provenance={
            "food_id": food_id,
            "nutrient_key": "protein",
            "amount": amount,
            "unit": "g",
            "basis_g": "100",
            "source": "external_source",
        },
    )


def test_valid_nutrient_has_complete_provenance():
    result = assess_food_quality(make_food([make_nutrient()]))

    assert result["assessment_status"] == "assessable"
    assert result["nutrient_summary"]["available"] == 1
    assert result["nutrients"][0]["status"] == "valid"
    assert result["nutrients"][0]["provenance_assessment"]["status"] == "complete"


def test_zero_is_a_valid_nutrient_value():
    result = assess_food_quality(make_food([make_nutrient(amount="0")]))

    assert result["nutrients"][0]["status"] == "valid"
    assert result["nutrient_summary"]["available"] == 1


def test_missing_nutrient_amount_is_counted_as_missing():
    result = assess_food_quality(make_food([make_nutrient(amount=None)]))

    assert result["nutrient_summary"]["missing"] == 1
    assert result["nutrients"][0]["status"] == "missing"
    assert result["nutrients"][0]["provenance_assessment"]["status"] == "invalid"


def test_negative_nutrient_is_invalid_in_both_assessments():
    result = assess_food_quality(make_food([make_nutrient(amount="-2")]))

    nutrient = result["nutrients"][0]
    assert nutrient["status"] == "negative_amount"
    assert nutrient["provenance_assessment"]["status"] == "invalid"
    assert result["assessment_status"] == "data_quality_issues"


def test_invalid_measurement_basis_is_invalid():
    result = assess_food_quality(make_food([make_nutrient(basis="0")]))

    assert result["nutrients"][0]["status"] == "invalid_basis"
    assert result["nutrient_summary"]["invalid"] == 1


def test_food_without_nutrient_records_has_no_nutrient_data():
    result = assess_food_quality(make_food())

    assert result["assessment_status"] == "no_nutrient_data"
    assert result["nutrient_summary"]["coverage_percent"] is None


def test_conflicting_indexed_evidence_is_reported():
    result = assess_food_quality(
        make_food([make_nutrient()]),
        [make_document()],
    )

    assert len(result["source_conflicts"]) == 1
    assert result["assessment_status"] == "data_quality_issues"


def test_evidence_for_another_food_is_ignored():
    result = assess_food_quality(
        make_food([make_nutrient()]),
        [make_document(food_id=999)],
    )

    assert result["source_conflicts"] == []


def test_stale_evidence_is_ignored():
    result = assess_food_quality(
        make_food([make_nutrient()]),
        [make_document(status="stale")],
    )

    assert result["source_conflicts"] == []


def test_regulatory_context_is_explicitly_not_assessed():
    result = assess_food_quality(make_food([make_nutrient()]))

    assert result["regulatory_context"]["status"] == "not_assessed"
