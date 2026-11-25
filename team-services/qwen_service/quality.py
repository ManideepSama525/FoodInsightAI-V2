"""Conservative, non-exhaustive guard. Not an allergy/nutrition guarantee."""
import re

_MEAT = re.compile(r'\b(chicken|beef|pork|mutton|lamb|fish|shrimp|prawn|bacon|ham|turkey)\b', re.I)
_VEGETARIAN = re.compile(r'\b(vegetable|vegetarian|vegan|veg\s+pulao|veg\s+biryani)\b', re.I)
_RICE = re.compile(r'\b(pulao|pilaf|biryani|fried rice)\b', re.I)

def check(title: str, result: dict) -> list[str]:
    problems = []
    ingredients = result.get('ingredients') or []
    steps = result.get('steps') or []
    if not result.get('format', {}).get('format_ok'):
        problems.append('Missing ingredients or numbered preparation steps')
    if not 3 <= len(ingredients) <= 35:
        problems.append('Unreasonable ingredient count')
    if not 3 <= len(steps) <= 20:
        problems.append('Incomplete preparation instructions')
    normalized = [re.sub(r'\s+', ' ', str(i).casefold().strip()) for i in ingredients]
    if len(normalized) != len(set(normalized)):
        problems.append('Repeated ingredients')
    if any(not x or len(x) > 180 for x in normalized):
        problems.append('Malformed ingredient entry')
    if _VEGETARIAN.search(title):
        if _MEAT.search(result.get('answer','')):
            problems.append('Meat/fish mentioned for a vegetarian or vegetable dish')
    if _RICE.search(title):
        if not re.search(r'\brice\b', result.get('answer', ''), re.I):
            problems.append('Rice dish does not mention rice')
    return problems
