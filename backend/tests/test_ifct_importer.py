from pathlib import Path

import pytest

from backend.app.integrations.ifct.importer import IFCTImportError, iter_ifct_foods


def test_imports_user_supplied_ifct_csv_and_keeps_trace_as_missing(tmp_path: Path) -> None:
    source = tmp_path / "ifct.csv"
    source.write_text(
        "food_code,food_name,nutrient_key,nutrient_name,amount_per_100g,unit\n"
        "A1,Red gram,protein,Protein,22.3,g\n"
        "A1,Red gram,vitamin_c,Vitamin C,trace,mg\n",
        encoding="utf-8",
    )
    foods = list(iter_ifct_foods(source))
    assert len(foods) == 1
    assert foods[0].source == "ifct"
    assert foods[0].external_id == "A1"
    assert float(foods[0].nutrients[0].amount) == 22.3
    assert foods[0].nutrients[1].amount is None


def test_rejects_missing_required_columns(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("food_name,amount\nRice,1\n", encoding="utf-8")
    with pytest.raises(IFCTImportError, match="missing required columns"):
        list(iter_ifct_foods(source))
