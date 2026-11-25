from backend.scripts.import_recipe_datasets import DISH_TITLE_ALIASES, match_dishes

class Dish:
    def __init__(self, dish_id, name):
        self.id = dish_id
        self.name = name
        self.normalized_name = name.casefold()
        self.is_active = True

def index(*names):
    return {name.casefold(): Dish(i + 1, name) for i, name in enumerate(names)}

def test_reviewed_recipe_title_aliases_match_only_canonical_dish():
    dishes = index("Caesar Salad", "Chicken Wings", "Greek Salad", "Spring Rolls")
    assert [d.name for d in match_dishes("Classic Caesar Salad Recipe", dishes)] == ["Caesar Salad"]
    assert [d.name for d in match_dishes("Grilled Chicken Wings Recipe", dishes)] == ["Chicken Wings"]
    assert [d.name for d in match_dishes("Classic Greek salad Recipe", dishes)] == ["Greek Salad"]
    assert [d.name for d in match_dishes("Vegetable Spring Rolls Recipe", dishes)] == ["Spring Rolls"]

def test_similar_but_different_titles_do_not_match():
    dishes = index("Apple Pie", "Carrot Cake", "Cheesecake")
    assert match_dishes("Apple Burfi Recipe", dishes) == []
    assert match_dishes("Carrot Chutney Recipe", dishes) == []
    assert match_dishes("Cheese Crackers Recipe", dishes) == []

def test_aliases_are_explicit_strings():
    assert "classic caesar salad" in DISH_TITLE_ALIASES["caesar salad"]
