from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _number(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def verify_nutrient_claim(
    claim: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    relative_tolerance: Decimal = Decimal("0.01"),
    absolute_tolerance: Decimal = Decimal("0.0001"),
) -> dict[str, Any]:
    """Verify numeric nutrient claims against attributed evidence."""
    if relative_tolerance < 0 or absolute_tolerance < 0:
        raise ValueError("Tolerances cannot be negative")

    food_id = claim.get("food_id")
    nutrient_key = claim.get("nutrient_key")
    expected = _number(claim.get("amount"))
    unit = str(claim.get("unit") or "").strip().lower()
    basis = _number(claim.get("basis_g"))

    if (
        food_id is None
        or not nutrient_key
        or expected is None
        or not unit
        or basis is None
        or basis <= 0
    ):
        raise ValueError(
            "Claim requires food_id, nutrient_key, numeric amount, "
            "unit and positive basis_g"
        )

    matching = []
    incomparable = []
    seen_measurements = set()

    for item in evidence:
        if item.get("source_type") != "nutrient":
            continue

        records = item.get("provenance_records") or [
            item.get("provenance") or {}
        ]

        for provenance in records:
            if (
                str(provenance.get("food_id")) != str(food_id)
                or str(provenance.get("nutrient_key")) != str(nutrient_key)
            ):
                continue

            observed = _number(provenance.get("amount"))
            observed_unit = str(
                provenance.get("unit") or ""
            ).strip().lower()
            observed_basis = _number(provenance.get("basis_g"))

            record = {
                "source_id": item.get("source_id"),
                "source": provenance.get("source"),
                "amount": str(observed) if observed is not None else None,
                "unit": observed_unit,
                "basis_g": (
                    str(observed_basis)
                    if observed_basis is not None else None
                ),
            }
            
            source = provenance.get("source")

            if (
                observed is None
                or not observed_unit
                or observed_basis is None
                or observed_basis <= 0
                or not isinstance(source, str)
                or not source.strip()
            ):
                incomparable.append(record)
                continue
            if observed_unit != unit or observed_basis != basis:
                incomparable.append(record)
                continue

            measurement_key = (
                record["source_id"],
                record["source"],
                provenance.get("source_nutrient_id"),
                observed,
                observed_unit,
                observed_basis,
            )

            if measurement_key in seen_measurements:
                continue

            seen_measurements.add(measurement_key)

            matching.append({
                **record,
                "_value": observed,
            })

    if not matching:
        return {
            "status": (
                "incomparable" if incomparable
                else "insufficient_evidence"
            ),
            "claim": dict(claim),
            "supporting_evidence": [],
            "incomparable_evidence": incomparable,
            "reason": (
                "Evidence exists but its measurement cannot be compared."
                if incomparable
                else "No matching nutrient evidence was found."
            ),
        }

    values = [record["_value"] for record in matching]
    minimum, maximum = min(values), max(values)
    scale = max(abs(expected), abs(minimum), abs(maximum), Decimal("1"))
    allowed = max(
        absolute_tolerance,
        relative_tolerance * scale,
    )

    evidence_disagrees = maximum - minimum > allowed
    claim_matches = any(
        abs(value - expected) <= allowed for value in values
    )

    if evidence_disagrees:
        status = "conflicting"
        reason = "Comparable evidence sources disagree."
    elif claim_matches:
        status = "supported"
        reason = "The claim matches comparable retrieved evidence."
    else:
        status = "conflicting"
        reason = "The claim contradicts comparable retrieved evidence."

    return {
        "status": status,
        "claim": dict(claim),
        "supporting_evidence": [
            {key: value for key, value in record.items() if key != "_value"}
            for record in matching
        ],
        "incomparable_evidence": incomparable,
        "reason": reason,
    }

