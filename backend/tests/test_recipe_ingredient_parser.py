from backend.scripts.ingredient_parser import parse_ingredient_cell


def test_indian_comma_separated_ingredients_split_on_quantity_boundaries():
    value = (
        "6 Karela (Bitter Gourd/ Pavakkai) - deseeded,"
        "Salt - to taste,1 Onion - thinly sliced,"
        "3 tablespoon Gram flour (besan),"
        "2 teaspoons Turmeric powder (Haldi)"
    )
    assert parse_ingredient_cell(value, comma_delimited=True) == [
        "6 Karela (Bitter Gourd/ Pavakkai) - deseeded",
        "Salt - to taste",
        "1 Onion - thinly sliced",
        "3 tablespoon Gram flour (besan)",
        "2 teaspoons Turmeric powder (Haldi)",
    ]


def test_descriptive_commas_remain_attached_to_ingredient():
    value = "2 onions, finely chopped, 1 cup tomatoes, roughly chopped"
    assert parse_ingredient_cell(value, comma_delimited=True) == [
        "2 onions, finely chopped",
        "1 cup tomatoes, roughly chopped",
    ]


def test_python_list_cell_is_parsed_without_splitting_descriptions():
    value = "['1 onion, finely chopped', 'Salt - to taste']"
    assert parse_ingredient_cell(value, comma_delimited=True) == [
        "1 onion, finely chopped",
        "Salt - to taste",
    ]


def test_ambiguous_unquantified_fragments_are_preserved():
    value = "some prepared masala, special finishing mixture"
    assert parse_ingredient_cell(value, comma_delimited=True) == [value]
