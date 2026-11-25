from decimal import Decimal, InvalidOperation
from typing import Any

ZERO = Decimal("0")


def nutrient_value_status(amount: Any, basis_g: Any) -> str:
    """Classify a nutrient measurement without modifying its source value.

    Returns: valid, missing, invalid_amount, negative_amount, invalid_basis.
    Zero is a valid measured value. Missing is not zero.
    """
    if amount is None:
        return "missing"

    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return "invalid_amount"

    if not value.is_finite():
        return "invalid_amount"
    if value < ZERO:
        return "negative_amount"

    if basis_g is None:
        return "invalid_basis"

    try:
        basis = Decimal(str(basis_g))
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return "invalid_basis"

    if not basis.is_finite() or basis <= ZERO:
        return "invalid_basis"

    return "valid"
