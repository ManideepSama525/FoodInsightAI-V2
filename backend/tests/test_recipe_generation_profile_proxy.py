"""Direct proxy contract tests: mocked Qwen; no live inference or GPU required."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.api.routes import recipe_generation as api


class UserDB:
    def __init__(self, profile=None, user_id=7):
        self.profile = profile
        self.user_id = user_id
        self.queries = []

    def scalar(self, query):
        params = query.compile().params
        assert self.user_id in params.values(), "Profile query must be scoped to current user"
        self.queries.append(query)
        return self.profile


def make_profile(**kw):
    defaults = dict(allergies=[], intolerances=[], dietary_preferences=[], disliked_foods=[])
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "success": True, "title": "Cucumber Salad", "answer": "A simple salad.",
            "ingredients": ["cucumber", "salt"], "steps": ["Slice cucumber", "Add salt"],
            "model": "Qwen3-4B", "adapter": None,
        }


class FakeClient:
    posts = []

    def __init__(self, **kwargs):
        assert kwargs.get("follow_redirects") is False
        assert kwargs.get("trust_env") is False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, json, headers):
        assert url == "http://host.docker.internal:8023/generate-recipe"
        assert set(json) == {"title", "max_new_tokens", "avoid_ingredients", "dietary_styles"}
        assert isinstance(json["avoid_ingredients"], list)
        assert isinstance(json["dietary_styles"], list)
        assert "severity" not in str(json)
        assert "user_id" not in str(json)
        assert set(headers) == {"X-Recipe-Service-Token"}  # no profile leakage
        self.posts.append(json)
        return FakeResponse()


@pytest.fixture(autouse=True)
def mock_inference(monkeypatch):
    monkeypatch.setenv("FOOD_RECIPE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("RECIPE_SERVICE_TOKEN", "x" * 40)
    monkeypatch.setenv("FOOD_RECIPE_INFERENCE_URL", "http://host.docker.internal:8023")
    monkeypatch.setattr(api.httpx, "Client", FakeClient)
    FakeClient.posts.clear()


def call(title, db):
    return api.generate_recipe(
        api.RecipeGenerationRequest(title=title), SimpleNamespace(id=7), db,
    )


def test_preflight_blocks_milk_allergy_without_inference_request():
    db = UserDB(make_profile(allergies=[{"name": "milk", "severity": "severe"}]))
    with pytest.raises(HTTPException) as e:
        call("Paneer curry", db)
    assert e.value.status_code == 409
    assert e.value.detail["code"] == "RECIPE_REQUEST_CONFLICT"
    assert FakeClient.posts == []
    assert len(db.queries) == 1


def test_different_user_profile_is_never_read():
    # Fake DB asserts the generated SQL contains the authenticated ID 7,
    # not any ID supplied by the request or the other user's ID 99.
    db = UserDB(make_profile(), user_id=7)
    out = call("Cucumber salad", db)
    assert out.safety.safe_to_assume is False
    assert len(db.queries) == 1


def test_missing_profile_returns_caution_without_safety_guarantee():
    out = call("Cucumber salad", UserDB(None))
    assert out.safety.status == "profile_missing"
    assert out.safety.safe_to_assume is False
    assert len(FakeClient.posts) == 1


def test_vegetarian_safe_generation_has_screening_record():
    out = call("Cucumber salad", UserDB(make_profile(dietary_preferences=["vegetarian"])))
    assert out.safety.safe_to_assume is False
    assert out.safety.status == "insufficient_evidence"


def test_postflight_detects_undeclared_peanut_in_cooking_steps(monkeypatch):
    def bad_json(self):
        return {
            "success": True, "title": "Cucumber Salad", "answer": "A simple salad.",
            "ingredients": ["cucumber", "salt"],
            "steps": ["Slice cucumber", "Add groundnut oil to taste"],
            "model": "Qwen3-4B", "adapter": None,
        }

    monkeypatch.setattr(FakeResponse, "json", bad_json)
    db = UserDB(make_profile(allergies=[{"name": "peanut", "severity": "severe"}]))
    with pytest.raises(HTTPException) as e:
        call("Cucumber salad", db)
    assert e.value.status_code == 409
    assert e.value.detail["code"] == "GENERATED_RECIPE_CONFLICT"


def test_proxy_preserves_inference_quality_gate_422(monkeypatch):
    monkeypatch.setattr(FakeResponse, "status_code", 422)
    try:
        with pytest.raises(HTTPException) as e:
            call("Cucumber salad", UserDB(make_profile()))
        assert e.value.status_code == 503
    finally:
        monkeypatch.setattr(FakeResponse, "status_code", 200)


def test_constraints_pass_to_local_qwen_without_profile_records():
    db = UserDB(make_profile(allergies=[{"name": "peanut", "severity": "severe"}],
                             dietary_preferences=["vegan"]))
    out = call("Cucumber salad", db)
    assert out.safety.safe_to_assume is False
    assert FakeClient.posts[0]["avoid_ingredients"] == ["peanut"]
    assert FakeClient.posts[0]["dietary_styles"] == ["vegan"]
    assert "severe" not in str(FakeClient.posts[0])
