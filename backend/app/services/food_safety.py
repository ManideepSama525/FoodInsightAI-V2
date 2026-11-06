import re
import unicodedata

from backend.app.schemas.food_profile import FoodProfileRead, FoodSafetyMatch, FoodSafetyRead


CONFIDENCE_THRESHOLD = 0.75

ALIASES = {
    "groundnut": "peanut",
    "groundnuts": "peanut",
    "arachis": "peanut",
    "peanuts": "peanut",
    "milk protein": "milk",
    "casein": "milk",
    "whey": "milk",
    "tree nut": "tree nuts",
    "almond": "tree nuts",
    "cashew": "tree nuts",
    "walnut": "tree nuts",
    "pistachio": "tree nuts",
    "hazelnut": "tree nuts",
    "pecan": "tree nuts",
    "brazil nut": "tree nuts",
    "macadamia": "tree nuts",
    "gluten": "wheat",
    "semolina": "wheat",
    "suji": "wheat",
    "sooji": "wheat",
    "atta": "wheat",
    "maida": "wheat",
    "gram flour": "chickpea",
    "besan": "chickpea",
    "soy": "soy",
    "soya": "soy",
    "prawn": "crustacean shellfish",
    "shrimp": "crustacean shellfish",
    "crab": "crustacean shellfish",
    "lobster": "crustacean shellfish",
}

ANIMAL_INGREDIENTS = {
    "chicken", "mutton", "lamb", "beef", "pork", "fish",
    "prawn", "shrimp", "crab", "lobster", "meat",
    "gelatin", "lard", "anchovy", "bacon", "ham",
}

DAIRY_INGREDIENTS = {
    "milk", "butter", "ghee", "cheese", "curd", "yogurt",
    "cream", "whey", "casein", "paneer",
}

EGG_INGREDIENTS = {"egg", "eggs", "mayonnaise"}

JAIN_ROOT_INGREDIENTS = {
    "onion", "garlic", "potato", "carrot", "beetroot",
    "radish", "turnip", "ginger", "turmeric root",
}

VEGAN_CONFLICTS = (
    ANIMAL_INGREDIENTS | DAIRY_INGREDIENTS | EGG_INGREDIENTS | {"honey"}
)
VEGETARIAN_CONFLICTS = ANIMAL_INGREDIENTS | {"gelatin", "lard"}
EGGETARIAN_CONFLICTS = ANIMAL_INGREDIENTS | {"gelatin", "lard"}
JAIN_CONFLICTS = (
    ANIMAL_INGREDIENTS | EGG_INGREDIENTS | JAIN_ROOT_INGREDIENTS
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower().strip()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical(value: str) -> str:
    value = normalize(value)
    return ALIASES.get(value, value)


def ingredient_matches_concern(ingredient: str, concern: str) -> bool:
    ingredient_norm = normalize(ingredient)
    concern_norm = canonical(concern)

    if not ingredient_norm or not concern_norm:
        return False

    # Normalize known aliases appearing inside compound ingredient names.
    candidates = {canonical(ingredient_norm)}
    for alias, target in ALIASES.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", ingredient_norm):
            candidates.add(target)

    if concern_norm in candidates:
        return True

    # Match a complete phrase, not an arbitrary substring.
    padded_ingredient = f" {ingredient_norm} "
    padded_concern = f" {concern_norm} "
    if padded_concern in padded_ingredient:
        return True

    # A broad profile concern such as "tree nuts" also matches its aliases.
    for alias, target in ALIASES.items():
        if target == concern_norm:
            if re.search(
                r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])",
                ingredient_norm,
            ):
                return True

    return False


def _certainty(confidence: float | None) -> str:
    if confidence is None or confidence < CONFIDENCE_THRESHOLD:
        return "possible"
    return "ingredient_list"


def _profile_read(profile) -> FoodProfileRead:
    from backend.app.schemas.food_profile import FoodProfileRead

    if profile is None:
        return FoodProfileRead()

    return FoodProfileRead(
        allergies=profile.allergies or [],
        intolerances=profile.intolerances or [],
        dietary_preferences=profile.dietary_preferences or [],
        goals=profile.goals or [],
        disliked_foods=profile.disliked_foods or [],
        cuisine_interests=profile.cuisine_interests or [],
        updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
    )


def assess_ingredients(ingredients: list[dict], profile) -> FoodSafetyRead:
    if profile is None:
        return FoodSafetyRead(
            status="profile_missing",
            safe_to_assume=False,
            matches=[],
            unknown_ingredients=[item["name"] for item in ingredients],
            disclaimer=(
                "No personal food profile exists. Ingredient completeness, "
                "cross-contact and hidden ingredients have not been verified."
            ),
        )

    matches: list[FoodSafetyMatch] = []
    unknown: list[str] = []

    for item in ingredients:
        name = item["name"]
        confidence = item.get("confidence")
        certainty = _certainty(confidence)

        if confidence is None or confidence < CONFIDENCE_THRESHOLD:
            unknown.append(name)

        for concern_type, entries in (
            ("allergy", profile.allergies or []),
            ("intolerance", profile.intolerances or []),
        ):
            for concern in entries:
                concern_name = concern["name"]
                if ingredient_matches_concern(name, concern_name):
                    severity = concern.get("severity", "unspecified")
                    matches.append(FoodSafetyMatch(
                        ingredient=name,
                        concern=concern_name,
                        concern_type=concern_type,
                        severity=severity,
                        certainty=certainty,
                        message=(
                            f"Possible {concern_type} conflict: {name} may contain "
                            f"{concern_name}."
                            if certainty == "possible"
                            else f"Ingredient-list conflict: {name} matches your recorded {concern_type}."
                        ),
                    ))

    preferences = {normalize(value) for value in (profile.dietary_preferences or [])}

    dietary_rules = []
    if "vegan" in preferences:
        dietary_rules.append(("vegan", VEGAN_CONFLICTS))
    if preferences.intersection({"vegetarian", "lacto vegetarian"}):
        dietary_rules.append(("vegetarian", VEGETARIAN_CONFLICTS))
    if "eggetarian" in preferences:
        dietary_rules.append(("eggetarian", EGGETARIAN_CONFLICTS))
    if "jain" in preferences:
        dietary_rules.append(("Jain", JAIN_CONFLICTS))

    for item in ingredients:
        name = item["name"]
        normalized = canonical(name)
        certainty = _certainty(item.get("confidence"))

        for preference, forbidden in dietary_rules:
            if normalized in forbidden:
                matches.append(FoodSafetyMatch(
                    ingredient=name,
                    concern=preference,
                    concern_type="dietary_preference",
                    severity="unspecified",
                    certainty=certainty,
                    message=f"{name} conflicts with your recorded {preference} preference.",
                ))

        for disliked in profile.disliked_foods or []:
            if ingredient_matches_concern(name, disliked):
                matches.append(FoodSafetyMatch(
                    ingredient=name,
                    concern=disliked,
                    concern_type="disliked_food",
                    severity="unspecified",
                    certainty=certainty,
                    message=f"{name} matches your disliked-food list.",
                ))

    has_allergy = any(match.concern_type == "allergy" for match in matches)
    has_other = bool(matches)

    if has_allergy:
        status = "allergy_conflict"
    elif has_other:
        status = "preference_conflict"
    elif unknown:
        status = "insufficient_evidence"
    else:
        status = "no_known_conflict"

    return FoodSafetyRead(
        status=status,
        safe_to_assume=False,
        matches=matches,
        unknown_ingredients=unknown,
        disclaimer=(
            "This is a screening aid, not a medical safety guarantee. Ingredient lists "
            "may be incomplete; cross-contact, processing aids and hidden ingredients "
            "are not assessed. Do not rely on image recognition to rule out an allergen. "
            "Verify packaging or the food provider, especially for severe allergies."
        ),
    )