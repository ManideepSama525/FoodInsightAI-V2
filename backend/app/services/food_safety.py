import re
import unicodedata

from backend.app.schemas.food_profile import FoodProfileRead, FoodSafetyMatch, FoodSafetyRead


CONFIDENCE_THRESHOLD = 0.75

ALIASES = {
    "groundnut": "peanut",
    "dairy": "milk",
    "paneer": "milk",
    "cottage cheese": "milk",
    "dahi": "milk",
    "lassi": "milk",
    "ricotta": "milk",
    "mozzarella": "milk",
    "feta": "milk",
    "cheese": "milk",
    "curd": "milk",
    "yogurt": "milk",
    "yoghurt": "milk",
    "ghee": "milk",
    "butter": "milk",
    "cream": "milk",
    "khoya": "milk",
    "mawa": "milk",
    "malai": "milk",
    "buttermilk": "milk",
    "egg whites": "egg",
    "egg yolks": "egg",
    "eggs": "egg",
    "tofu": "soy",
    "tempeh": "soy",
    "edamame": "soy",
    "soybean": "soy",
    "soybeans": "soy",
    "soya chunks": "soy",
    "soy sauce": "soy",
    "soya sauce": "soy",
    "almonds": "tree nuts",
    "cashews": "tree nuts",
    "walnuts": "tree nuts",
    "pistachios": "tree nuts",
    "hazelnuts": "tree nuts",
    "prawns": "crustacean shellfish",
    "shrimps": "crustacean shellfish",
    "oyster": "molluscan shellfish",
    "mussels": "molluscan shellfish",
    "clams": "molluscan shellfish",
    "scallop": "molluscan shellfish",
    "scallops": "molluscan shellfish",
    "salmon": "fish",
    "tuna": "fish",
    "cod": "fish",
    "sardine": "fish",
    "sardines": "fish",
    "tilapia": "fish",
    "rohu": "fish",
    "pomfret": "fish",
    "mackerel": "fish",
    "anchovy": "fish",
    "anchovies": "fish",
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
    "chicken stock", "chicken broth", "meat stock", "fish stock",
    "fish sauce", "oyster sauce", "salmon", "tuna", "cod", "sardine",
    "tilapia", "rohu", "pomfret", "mackerel", "anchovies", "scallop",
}

DAIRY_INGREDIENTS = {
    "milk", "butter", "ghee", "cheese", "curd", "yogurt",
    "cream", "whey", "casein", "paneer", "buttermilk",
    "khoya", "mawa", "malai", "yoghurt", "dahi", "lassi",
}

EGG_INGREDIENTS = {"egg", "eggs", "mayonnaise", "egg white", "egg yolk"}

JAIN_ROOT_INGREDIENTS = {
    "onion", "onions", "garlic", "potato", "potatoes", "carrot", "carrots", "beetroot", "beetroots",
    "radish", "radishes", "turnip", "turnips", "ginger", "turmeric root",
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


_PLANT_MILK = re.compile(
    r"\b(?:coconut|almond|soy|soya|oat|rice|cashew|pea|hemp)\s+milk\b"
)
_NUT_BUTTER = re.compile(r"\b(?:peanut|groundnut|almond|cashew|sunflower)\s+butter\b")


def _mentions(name: str, term: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", name))


def _is_exclusively_plant_milk(name: str) -> bool:
    # Only omit the word 'milk' when every milk mention is explicitly plant-based.
    plant_count = len(_PLANT_MILK.findall(name))
    milk_count = len(re.findall(r"\bmilk\b", name))
    other_text = _NUT_BUTTER.sub("", name).replace("coconut cream", "")
    dairy_others = (
        "paneer", "ghee", "cheese", "curd", "yogurt", "yoghurt",
        "casein", "whey", "butter", "malai", "mawa", "khoya", "cream",
        "dahi", "lassi", "ricotta", "mozzarella", "feta", "buttermilk",
    )
    return bool(milk_count and milk_count == plant_count and not any(
        _mentions(other_text, token) for token in dairy_others
    ))


def _term_in_ingredient(name: str, token: str) -> bool:
    if not _mentions(name, token):
        return False
    if token == "milk" and _is_exclusively_plant_milk(name):
        return False
    if token == "butter" and _NUT_BUTTER.search(name) and not _mentions(
        _NUT_BUTTER.sub("", name), "butter"
    ):
        return False
    if token == "cream" and _mentions(name, "coconut cream") and not _mentions(
        name.replace("coconut cream", ""), "cream"
    ):
        return False
    return True


def ingredient_matches_concern(ingredient: str, concern: str) -> bool:
    ingredient_norm = normalize(ingredient)
    concern_norm = canonical(concern)
    if not ingredient_norm or not concern_norm:
        return False

    # Wheat allergy and gluten sensitivity are distinct; barley/rye do not
    # imply wheat-protein exposure, but do matter for a gluten restriction.
    if concern_norm == "gluten":
        return any(_mentions(ingredient_norm, word) for word in (
            "gluten", "wheat", "barley", "rye", "spelt", "atta",
            "maida", "semolina", "suji", "sooji", "durum",
        ))
    if concern_norm == "lactose":
        return any(_term_in_ingredient(ingredient_norm, word) for word in (
            "lactose", "milk", "paneer", "curd", "yogurt", "yoghurt",
            "buttermilk", "cream", "khoya", "mawa", "malai",
        ))

    # A plant-based milk is not automatically a milk-protein allergen.
    if concern_norm == "milk" and _is_exclusively_plant_milk(ingredient_norm):
        return False

    if _term_in_ingredient(ingredient_norm, concern_norm):
        return True
    for alias, target in ALIASES.items():
        if target == concern_norm and _term_in_ingredient(ingredient_norm, alias):
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
                            "Paneer is made from milk and conflicts with your recorded milk allergy."
                            if concern_type == "allergy" and canonical(concern_name) == "milk"
                            and _mentions(normalize(name), "paneer")
                            else (
                                f"Possible {concern_type} conflict: {name} may contain "
                                f"{concern_name}."
                                if certainty == "possible"
                                else f"Ingredient-list conflict: {name} matches your recorded {concern_type}."
                            )
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
            if any(_term_in_ingredient(normalized, token) for token in forbidden):
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