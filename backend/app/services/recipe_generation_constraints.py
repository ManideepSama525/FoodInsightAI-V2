"""Minimize Food Profile information sent to the *local* recipe-inference service.

Only fixed, canonical restriction categories are forwarded, never profile rows,
free-text medical information, severity, names, IDs or account metadata.
The separate deterministic backend assessment remains authoritative for warnings.
"""
from backend.app.services.food_safety import canonical, normalize

KNOWN_AVOID = frozenset({
    "milk", "egg", "peanut", "tree nuts", "wheat", "gluten", "soy",
    "fish", "crustacean shellfish", "molluscan shellfish", "sesame",
    "lactose", "chickpea", "onion", "garlic", "mustard", "celery",
})
KNOWN_DIET = frozenset({"vegan", "vegetarian", "jain", "eggetarian"})


def build_constraints(profile) -> dict[str, list[str]]:
    if profile is None:
        return {"avoid_ingredients": [], "dietary_styles": []}
    avoid = set()
    for field in ("allergies", "intolerances"):
        for entry in (getattr(profile, field, None) or []):
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                category = canonical(entry["name"])
                if category in KNOWN_AVOID:
                    avoid.add(category)
    # Disliked foods are personal choices, not medically verified allergens.
    # Only send standardized ingredient labels; never raw custom free text.
    for entry in (getattr(profile, "disliked_foods", None) or []):
        if isinstance(entry, str):
            category = canonical(entry)
            if category in KNOWN_AVOID:
                avoid.add(category)

    styles = set()
    for preference in (getattr(profile, "dietary_preferences", None) or []):
        if not isinstance(preference, str):
            continue
        p = normalize(preference)
        if p in KNOWN_DIET:
            styles.add(p)
        if p == "lacto vegetarian":
            styles.add("vegetarian")
    return {
        "avoid_ingredients": sorted(avoid)[:20],
        "dietary_styles": sorted(styles),
    }
