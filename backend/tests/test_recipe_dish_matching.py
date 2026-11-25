from types import SimpleNamespace

from backend.scripts.import_recipe_datasets import match_dishes, normalize


def test_exact_canonical_dish_title_matches():
    dish = SimpleNamespace(id=1, name="Pizza", normalized_name="pizza")
    assert match_dishes("Pizza", {"pizza": dish}) == [dish]


def test_explicit_curated_alias_matches_canonical_dish():
    dish = SimpleNamespace(id=2, name="Chole Bhature", normalized_name="chole bhature")
    assert match_dishes("Chole Bhatura", {"chole bhature": dish}) == [dish]


def test_partial_title_does_not_create_dish_association():
    dish = SimpleNamespace(id=3, name="Biryani", normalized_name="biryani")
    assert match_dishes("Biryani with raita", {"biryani": dish}) == []


def test_unrelated_ingredient_overlap_never_matches():
    dish = SimpleNamespace(id=4, name="Dosa", normalized_name="dosa")
    assert match_dishes("Rice and lentil pancake", {"dosa": dish}) == []


def test_terminal_recipe_suffix_is_accepted_as_exact_title():
    dish = SimpleNamespace(id=5, name="Pizza", normalized_name="pizza")
    assert match_dishes("Pizza Recipe", {"pizza": dish}) == [dish]
