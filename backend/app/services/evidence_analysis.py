from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
from typing import Any


def aggregate_evidence(
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize and deduplicate evidence while preserving provenance."""
    aggregated: dict[tuple[str, str], dict[str, Any]] = {}

    for item in evidence:
        source_type = item.get("source_type")
        source_id = str(item.get("source_id") or "")

        if not source_type or not source_id:
            continue

        key = (source_type, source_id)

        if key not in aggregated:
            aggregated[key] = {
                **item,
                "provenance": dict(item.get("provenance") or {}),
                "provenance_records": [
                    dict(record)
                    for record in (
                        item.get("provenance_records")
                        or ([item["provenance"]] if item.get("provenance") else [])
                    )
                ],
                "retrieval_sources": list(
                    dict.fromkeys(item.get("retrieval_sources") or [])
                ),
                "source_ranks": dict(item.get("source_ranks") or {}),
            }
            continue

        current = aggregated[key]

        incoming_records = item.get("provenance_records") or (
            [item["provenance"]] if item.get("provenance") else []
        )
        existing_keys = {
            json.dumps(record, sort_keys=True, default=str)
            for record in current["provenance_records"]
        }
        for record in incoming_records:
            provenance_key = json.dumps(
                record, sort_keys=True, default=str
            )
            if provenance_key not in existing_keys:
                current["provenance_records"].append(dict(record))
                existing_keys.add(provenance_key)

        for channel in item.get("retrieval_sources") or []:
            if channel not in current["retrieval_sources"]:
                current["retrieval_sources"].append(channel)

        current["source_ranks"].update(item.get("source_ranks") or {})

        # Never overwrite existing source attribution with an empty value.
        if not current.get("provenance") and item.get("provenance"):
            current["provenance"] = dict(item["provenance"])

        if not current.get("content") and item.get("content"):
            current["content"] = item["content"]

        if not current.get("title") and item.get("title"):
            current["title"] = item["title"]

        if not current.get("content_hash") and item.get("content_hash"):
            current["content_hash"] = item["content_hash"]

    return sorted(
        aggregated.values(),
        key=lambda item: (
            -float(item.get("rank_score") or 0),
            item["source_type"],
            item["source_id"],
        ),
    )


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None

    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if not result.is_finite():
        return None

    return result


def detect_source_conflicts(
    evidence: list[dict[str, Any]],
    *,
    relative_tolerance: Decimal = Decimal("0.01"),
    absolute_tolerance: Decimal = Decimal("0.0001"),
) -> dict[str, list[dict[str, Any]]]:
    """Compare nutrient evidence across all retained provenance records."""
    if relative_tolerance < 0 or absolute_tolerance < 0:
        raise ValueError("Tolerances cannot be negative")

    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    incomparable: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []

    for item in evidence:
        if item.get("source_type") != "nutrient":
            continue

        records = item.get("provenance_records") or [
            item.get("provenance") or {}
        ]

        for provenance in records:
            food_id = provenance.get("food_id")
            nutrient_key = provenance.get("nutrient_key")
            amount = _decimal(provenance.get("amount"))
            unit = str(provenance.get("unit") or "").strip().lower()
            basis = _decimal(provenance.get("basis_g"))

            if food_id is None or not nutrient_key:
                continue

            if amount is None or not unit or basis is None or basis <= 0:
                invalid.append({
                    "food_id": food_id,
                    "nutrient_key": nutrient_key,
                    "source_id": item.get("source_id"),
                    "source": provenance.get("source"),
                    "reason": "Missing or invalid amount, unit or measurement basis.",
                })
                continue

            key = (str(food_id), str(nutrient_key))
            record = {
                "source_id": item.get("source_id"),
                "source": provenance.get("source"),
                "amount": amount,
                "unit": unit,
                "basis_g": basis,
            }
            if record not in groups[key]:
                groups[key].append(record)

    conflicts: list[dict[str, Any]] = []

    for (food_id, nutrient_key), records in groups.items():
        if len(records) < 2:
            continue

        measurement_groups: dict[tuple[str, Decimal], list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            measurement_groups[(record["unit"], record["basis_g"])].append(record)

        if len(measurement_groups) > 1:
            incomparable.append({
                "food_id": food_id,
                "nutrient_key": nutrient_key,
                "reason": "Evidence uses different units or measurement bases.",
                "measurements": [
                    {
                        "unit": unit,
                        "basis_g": str(basis),
                        "source_ids": [record["source_id"] for record in values],
                    }
                    for (unit, basis), values in measurement_groups.items()
                ],
            })

        for (unit, basis), values in measurement_groups.items():
            if len(values) < 2:
                continue

            amounts = [record["amount"] for record in values]
            minimum, maximum = min(amounts), max(amounts)
            difference = maximum - minimum
            scale = max(abs(minimum), abs(maximum), Decimal("1"))
            allowed = max(absolute_tolerance, relative_tolerance * scale)

            if difference > allowed:
                conflicts.append({
                    "food_id": food_id,
                    "nutrient_key": nutrient_key,
                    "unit": unit,
                    "basis_g": str(basis),
                    "reason": "Conflicting values for the same measurement basis.",
                    "values": [
                        {
                            "source_id": record["source_id"],
                            "source": record["source"],
                            "amount": str(record["amount"]),
                        }
                        for record in values
                    ],
                    "difference": str(difference),
                })

    return {
        "conflicts": conflicts,
        "incomparable": incomparable,
        "invalid_evidence": invalid,
    }

def assess_provenance_quality(
    item: dict[str, Any],
) -> dict[str, Any]:
    """Assess attribution and measurement completeness, not source authority."""
    source_type = item.get("source_type")
    records = item.get("provenance_records") or [
        item.get("provenance") or {}
    ]

    if not records or records == [{}]:
        return {
            "status": (
                "invalid" if source_type == "nutrient" else "partial"
            ),
            "records_assessed": 1 if source_type == "nutrient" else 0,
            "issues": ["No provenance records are available."],
            "optional_metadata_unavailable": [],
        }

    issues: list[str] = []
    optional_unavailable: list[str] = []
    invalid_measurement = False

    for index, record in enumerate(records):
        prefix = f"Provenance record {index + 1}"

        if not isinstance(record, dict):
            issues.append(f"{prefix} is not a valid object.")
            invalid_measurement = source_type == "nutrient"
            continue

        if source_type == "nutrient":
            for field in ("food_id", "nutrient_key", "source"):
                if record.get(field) is None or str(record.get(field)).strip() == "":
                    issues.append(f"{prefix} is missing {field}.")

            amount = _decimal(record.get("amount"))
            basis = _decimal(record.get("basis_g"))
            unit = str(record.get("unit") or "").strip()

            if amount is None:
                issues.append(f"{prefix} has a missing or invalid amount.")
                invalid_measurement = True

            if not unit:
                issues.append(f"{prefix} has a missing measurement unit.")
                invalid_measurement = True

            if basis is None or basis <= 0:
                issues.append(f"{prefix} has a missing or invalid measurement basis.")
                invalid_measurement = True

            # USDA FNDDS records may legitimately lack derivation metadata.
            if not record.get("derivation_code"):
                optional_unavailable.append(
                    f"{prefix}: derivation metadata unavailable."
                )

        elif source_type == "food":
            if not record.get("source"):
                issues.append(f"{prefix} is missing source attribution.")

            if (
                record.get("food_id") is None
                and record.get("external_id") is None
            ):
                issues.append(
                    f"{prefix} has no food or external source identifier."
                )

        elif source_type == "shared_recipe":
            if record.get("owner_scope") != "shared":
                issues.append(
                    f"{prefix} does not explicitly establish shared ownership."
                )

            if not record.get("source"):
                issues.append(f"{prefix} is missing source attribution.")

        else:
            if not record:
                issues.append(f"{prefix} contains no provenance information.")

    if invalid_measurement:
        status = "invalid"
    elif issues:
        status = "partial"
    else:
        status = "complete"

    return {
        "status": status,
        "records_assessed": len(records),
        "issues": list(dict.fromkeys(issues)),
        "optional_metadata_unavailable": list(
            dict.fromkeys(optional_unavailable)
        ),
    }

