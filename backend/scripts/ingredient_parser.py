"""Conservative parsers for source recipe ingredient fields."""
from __future__ import annotations
import ast
import re

_UNQUANTIFIED_STARTS = {
    "salt", "water", "oil", "olive oil", "vegetable oil", "sunflower oil",
    "coconut oil", "mustard oil", "ghee", "butter", "pepper", "black pepper",
    "white pepper", "turmeric", "turmeric powder", "red chilli powder",
    "red chili powder", "chilli powder", "chili powder", "cumin", "cumin seeds",
    "coriander", "coriander powder", "coriander seeds", "garam masala",
    "asafoetida", "hing", "hing powder", "mustard seeds", "fenugreek seeds",
    "curry leaves", "coriander leaves", "cilantro", "mint leaves", "lemon juice",
    "lime juice", "sugar", "jaggery", "honey", "vinegar", "baking soda",
    "baking powder", "yeast", "vanilla extract", "tomato ketchup",
}
_NUMBER = r"(?:\d+\s*-\s*\d+\s*/\s*\d+|\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?|[½¼¾])"
_QUANTITY_START = re.compile(
    rf"^\s*{_NUMBER}\s*(?:kg|grams?|g|mg|ml|l|cups?|tbsp\.?|tablespoons?|"
    r"tsp\.?|teaspoons?|pieces?|cloves?|slices?|pinches?|ounces?|oz|"
    r"pounds?|lb|sprigs?|bunch(?:es)?|inches?)?\b", re.I
)

def _is_new_item(fragment: str) -> bool:
    candidate = fragment.strip().lstrip("-• ")
    if not candidate:
        return False
    if _QUANTITY_START.match(candidate):
        return True
    folded = candidate.casefold()
    return any(
        folded == start or folded.startswith(start + " ") or
        folded.startswith(start + " -")
        for start in _UNQUANTIFIED_STARTS
    )

def parse_ingredient_cell(value: str | None, *, comma_delimited: bool = False) -> list[str]:
    """Parse source cells conservatively; retain uncertain fragments."""
    if not value or not value.strip():
        return []
    text = value.strip()
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple)):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except (ValueError, SyntaxError):
        pass
    if not comma_delimited:
        return [part.strip() for part in re.split(r"[\r\n]+", text) if part.strip()]
    fragments = [part.strip() for part in text.split(",")]
    items: list[str] = []
    current = ""
    for fragment in fragments:
        if not fragment:
            continue
        if current and _is_new_item(fragment):
            items.append(current.strip())
            current = fragment
        elif current:
            current += ", " + fragment
        else:
            current = fragment
    if current.strip():
        items.append(current.strip())
    return items
