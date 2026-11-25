from types import SimpleNamespace

import pytest

from backend.app.services import hybrid_retrieval as hybrid


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def unique(self):
        return self


class FakeDB:
    def __init__(self, *results):
        self.results = list(results)

    def scalars(self, statement):
        if not self.results:
            raise AssertionError("Unexpected SQL query")
        return FakeResult(self.results.pop(0))


def evidence(source_type, source_id, provenance=None):
    return SimpleNamespace(
        source_type=source_type,
        source_id=source_id,
        title=f"Evidence {source_id}",
        content=f"Content {source_id}",
        provenance=provenance or {},
        content_hash=f"hash-{source_id}",
    )


def test_tokens_normalize_and_deduplicate():
    assert hybrid._tokens("Hummus HUMMUS, Protein 100g!") == [
        "hummus", "protein", "100g"
    ]


def test_empty_query_is_rejected():
    with pytest.raises(ValueError, match="query cannot be empty"):
        hybrid.retrieve_hybrid_evidence(FakeDB(), "   ")


@pytest.mark.parametrize("top_k", [0, 51, -1, True, 1.5, "5"])
def test_invalid_top_k_is_rejected(top_k):
    with pytest.raises(ValueError, match="top_k"):
        hybrid.retrieve_hybrid_evidence(FakeDB(), "hummus", top_k=top_k)


def test_sql_and_vector_results_are_fused_and_deduplicated(monkeypatch):
    sql_food = evidence("food", "12", {
        "source": "usda_fdc",
        "external_id": "123",
    })

    db = FakeDB([sql_food], [])

    monkeypatch.setattr(hybrid.knowledge_graph, "_driver", None)
    monkeypatch.setattr(
        hybrid,
        "search_evidence",
        lambda query, top_k: [{
            "source_type": "food",
            "source_id": "12",
            "title": "Hummus",
            "content": "Food: Hummus",
            "provenance": {"source": "usda_fdc"},
            "content_hash": "hash-12",
            "score": 0.91,
        }],
    )

    results = hybrid.retrieve_hybrid_evidence(db, "hummus", top_k=5)

    assert len(results) == 1
    assert results[0]["source_id"] == "12"
    assert set(results[0]["retrieval_sources"]) == {"sql", "vector"}
    assert results[0]["rank_score"] > 0
    assert results[0]["similarity_score"] == pytest.approx(0.91)
    assert results[0]["provenance"]["external_id"] == "123"


def test_private_recipe_is_excluded_from_sql_and_vector(monkeypatch):
    private_recipe = evidence(
        "shared_recipe",
        "99",
        {"owner_scope": "private", "user_id": 7},
    )

    db = FakeDB([private_recipe], [])

    monkeypatch.setattr(hybrid.knowledge_graph, "_driver", None)
    monkeypatch.setattr(
        hybrid,
        "search_evidence",
        lambda query, top_k: [{
            "source_type": "shared_recipe",
            "source_id": "99",
            "title": "Private recipe",
            "content": "Private recipe content",
            "provenance": {"owner_scope": "private", "user_id": 7},
        }],
    )

    results = hybrid.retrieve_hybrid_evidence(db, "recipe")

    assert results == []


def test_shared_recipe_is_eligible():
    assert hybrid._eligible_recipe({
        "source_type": "shared_recipe",
        "provenance": {"owner_scope": "shared"},
    })

    assert not hybrid._eligible_recipe({
        "source_type": "shared_recipe",
        "provenance": {"owner_scope": "private"},
    })


def test_graph_nutrient_evidence_preserves_measurement_provenance(monkeypatch):
    food = SimpleNamespace(
        id=5,
        name="Hummus",
        normalized_name="hummus",
        category=None,
        description="Chickpea spread",
        source="usda_fdc",
        source_url="https://example.test/food/5",
        external_id="FDC-5",
    )

    neighborhood = {
        "food": {"name": "Hummus"},
        "nutrients": [{
            "key": "protein",
            "name": "Protein",
            "amount": 8.5,
            "unit": "g",
            "basis_g": 100.0,
            "source": "usda_fdc",
            "source_nutrient_id": "1003",
            "derivation_code": "NC",
            "derivation_description": "Calculated",
            "derivation_source_description": "Calculated from component nutrients",
        }],
    }

    db = FakeDB([], [food])

    monkeypatch.setattr(hybrid.knowledge_graph, "_driver", object())
    monkeypatch.setattr(
        hybrid.knowledge_graph,
        "food_neighborhood",
        lambda food_id: neighborhood if food_id == 5 else None,
    )
    monkeypatch.setattr(hybrid, "search_evidence", lambda query, top_k: [])

    results = hybrid.retrieve_hybrid_evidence(db, "hummus", top_k=10)

    nutrient = next(
        item for item in results
        if item["source_type"] == "nutrient"
    )

    assert nutrient["source_id"] == "5:protein"
    assert nutrient["provenance"]["amount"] == "8.5"
    assert nutrient["provenance"]["unit"] == "g"
    assert nutrient["provenance"]["basis_g"] == "100.0"
    assert "graph" in nutrient["retrieval_sources"]
    assert nutrient["provenance"]["source_nutrient_id"] == "1003"
    assert nutrient["provenance"]["derivation_code"] == "NC"
    assert nutrient["provenance"]["derivation_description"] == "Calculated"
    assert (
        nutrient["provenance"]["derivation_source_description"]
        == "Calculated from component nutrients"
    )


def test_reciprocal_rank_fusion_rewards_multiple_channels():
    candidates = {}

    hybrid._merge_candidate(
        candidates,
        {"source_type": "food", "source_id": "1", "title": "Food"},
        "sql",
        1,
    )
    hybrid._merge_candidate(
        candidates,
        {"source_type": "food", "source_id": "1", "title": "Food"},
        "vector",
        1,
    )
    hybrid._merge_candidate(
        candidates,
        {"source_type": "food", "source_id": "2", "title": "Other"},
        "sql",
        1,
    )

    assert (
        candidates[("food", "1")]["rank_score"]
        > candidates[("food", "2")]["rank_score"]
    )
def test_hybrid_retrieval_detects_conflicting_nutrient_sources(monkeypatch):
    sql_nutrient = evidence("nutrient", "5:protein", {
        "food_id": 5,
        "nutrient_key": "protein",
        "amount": "8.5",
        "unit": "g",
        "basis_g": "100",
        "source": "USDA",
    })

    vector_nutrient = {
        "source_type": "nutrient",
        "source_id": "5:protein",
        "title": "Protein in Hummus",
        "content": "Protein: 10 g per 100 g",
        "provenance": {
            "food_id": 5,
            "nutrient_key": "protein",
            "amount": "10",
            "unit": "g",
            "basis_g": "100",
            "source": "Secondary source",
        },
        "score": 0.91,
    }

    db = FakeDB([sql_nutrient], [])

    monkeypatch.setattr(hybrid.knowledge_graph, "_driver", None)
    monkeypatch.setattr(
        hybrid,
        "search_evidence",
        lambda query, top_k: [vector_nutrient],
    )

    results = hybrid.retrieve_hybrid_evidence(db, "hummus protein")

    nutrient = next(
        item for item in results
        if item["source_type"] == "nutrient"
    )

    assert set(nutrient["retrieval_sources"]) == {"sql", "vector"}
    assert len(nutrient["provenance_records"]) == 2
    assert len(nutrient["source_conflicts"]) == 1
    assert nutrient["source_conflicts"][0]["unit"] == "g"
    assert nutrient["source_conflicts"][0]["basis_g"] == "100"
    assert nutrient["incomparable_measurements"] == []


def test_hybrid_retrieval_marks_different_measurement_bases_incomparable(
    monkeypatch,
):
    sql_nutrient = evidence("nutrient", "5:protein", {
        "food_id": 5,
        "nutrient_key": "protein",
        "amount": "8.5",
        "unit": "g",
        "basis_g": "100",
        "source": "USDA",
    })

    vector_nutrient = {
        "source_type": "nutrient",
        "source_id": "5:protein",
        "title": "Protein in Hummus",
        "content": "Protein: 17 g per 200 g",
        "provenance": {
            "food_id": 5,
            "nutrient_key": "protein",
            "amount": "17",
            "unit": "g",
            "basis_g": "200",
            "source": "Secondary source",
        },
        "score": 0.90,
    }

    db = FakeDB([sql_nutrient], [])

    monkeypatch.setattr(hybrid.knowledge_graph, "_driver", None)
    monkeypatch.setattr(
        hybrid,
        "search_evidence",
        lambda query, top_k: [vector_nutrient],
    )

    results = hybrid.retrieve_hybrid_evidence(db, "hummus protein")

    nutrient = next(
        item for item in results
        if item["source_type"] == "nutrient"
    )

    assert nutrient["source_conflicts"] == []
    assert len(nutrient["incomparable_measurements"]) == 1
    assert len(nutrient["incomparable_measurements"][0]["measurements"]) == 2


def test_tokens_remove_question_stopwords():
    assert hybrid._tokens(
        "What nutrients are present in hummus?"
    ) == ["nutrients", "hummus"]


def test_food_anchor_ids_match_explicit_food_names():
    foods = [
        SimpleNamespace(id=1, name="Hummus, commercial", normalized_name="hummus"),
        SimpleNamespace(id=158, name="Almond milk", normalized_name="almond milk"),
    ]

    assert hybrid._food_anchor_ids(
        foods, hybrid._tokens("What nutrients are present in hummus?")
    ) == {"1"}


def test_food_anchor_ids_require_complete_multiword_food_phrase():
    foods = [
        SimpleNamespace(id=133, name="Soy milk, unsweetened, plain, shelf stable",
                        normalized_name="soy milk unsweetened plain shelf stable"),
        SimpleNamespace(id=158, name="Almond milk", normalized_name="almond milk"),
        SimpleNamespace(id=210, name="Soy flour, defatted", normalized_name="soy flour defatted"),
    ]

    assert hybrid._food_anchor_ids(
        foods, hybrid._tokens("What is the fiber content of soy milk?")
    ) == {"133"}


def test_food_anchor_ids_do_not_match_partial_multiword_phrase():
    foods = [
        SimpleNamespace(id=158, name="Almond milk", normalized_name="almond milk"),
        SimpleNamespace(id=210, name="Soy flour, defatted", normalized_name="soy flour defatted"),
    ]

    assert hybrid._food_anchor_ids(
        foods, hybrid._tokens("What is the fiber content of soy milk?")
    ) == set()


def test_food_anchor_filter_excludes_unrelated_food_evidence():
    candidates = {
        ("food", "1"): {
            "source_type": "food",
            "source_id": "1",
        },
        ("food", "158"): {
            "source_type": "food",
            "source_id": "158",
        },
        ("nutrient", "1:protein"): {
            "source_type": "nutrient",
            "source_id": "1:protein",
            "provenance_records": [{"food_id": 1}],
        },
        ("nutrient", "158:protein"): {
            "source_type": "nutrient",
            "source_id": "158:protein",
            "provenance_records": [{"food_id": 158}],
        },
        ("shared_recipe", "9"): {
            "source_type": "shared_recipe",
            "source_id": "9",
        },
    }

    filtered = hybrid._filter_candidates_to_food_anchors(
        candidates, {"1"}
    )

    assert set(filtered) == {
        ("food", "1"),
        ("nutrient", "1:protein"),
        ("shared_recipe", "9"),
    }


def test_general_nutrition_query_prioritizes_primary_nutrients():
    results = [
        {"source_type": "nutrient", "source_id": "nitrogen",
         "provenance": {"nutrient_key": "usda_1002", "amount": 1.18}},
        {"source_type": "nutrient", "source_id": "sfa",
         "provenance": {"nutrient_key": "usda_1265", "amount": 1.41}},
        {"source_type": "nutrient", "source_id": "protein",
         "provenance": {"nutrient_key": "protein", "amount": 7.35}},
        {"source_type": "nutrient", "source_id": "energy",
         "provenance": {"nutrient_key": "energy_kcal", "amount": 229}},
        {"source_type": "food", "source_id": "1"},
    ]

    ranked = hybrid._rank_general_nutrition_results(
        results, "What nutrients are present in hummus?"
    )

    assert [item["source_id"] for item in ranked] == [
        "1", "energy", "protein", "nitrogen", "sfa"
    ] or [item["source_id"] for item in ranked][:3] == [
        "1", "energy", "protein"
    ]


def test_specific_nutrient_query_prioritizes_requested_nutrient():
    results = [
        {
            "source_type": "nutrient",
            "source_id": "sfa",
            "title": "Monounsaturated fatty acids in Hummus",
            "provenance": {"nutrient_key": "usda_1265"},
            "rank_score": 0.9,
        },
        {
            "source_type": "nutrient",
            "source_id": "protein",
            "title": "Protein in Hummus",
            "provenance": {"nutrient_key": "protein"},
            "rank_score": 0.2,
        },
    ]

    ranked = hybrid._rank_general_nutrition_results(
        results, "How much protein is in hummus?"
    )

    assert ranked[0]["source_id"] == "protein"


def test_specific_fiber_query_prioritizes_fiber():
    results = [
        {
            "source_type": "nutrient",
            "source_id": "protein",
            "title": "Protein in Soy milk",
            "provenance": {"nutrient_key": "protein"},
        },
        {
            "source_type": "nutrient",
            "source_id": "fiber",
            "title": "Fiber in Soy milk",
            "provenance": {"nutrient_key": "fiber"},
        },
    ]

    ranked = hybrid._rank_general_nutrition_results(
        results, "What is the fiber content of soy milk?"
    )

    assert ranked[0]["source_id"] == "fiber"

def test_regulatory_evidence_is_allowed_and_unverified_evidence_is_rejected():
    valid_provenance = {
        "record_type": "regulatory_evidence",
        "official_domain_validated": True,
        "authority": "FSSAI",
        "jurisdiction": "India",
        "source_url": "https://www.fssai.gov.in/notice",
        "document_type": "guidance",
        "document_status": "active",
        "published_at": "2026-11-01T00:00:00+00:00",
        "last_checked_at": "2026-11-13T00:00:00+00:00",
    }
    candidates = {}
    hybrid._merge_candidate(
        candidates,
        {
            "source_type": "regulatory",
            "source_id": "NOTICE-1",
            "title": "Food safety guidance",
            "content": "Official food safety guidance",
            "provenance": valid_provenance,
        },
        "sql",
        1,
    )
    hybrid._merge_candidate(
        candidates,
        {
            "source_type": "regulatory",
            "source_id": "NOTICE-2",
            "title": "Unverified notice",
            "content": "Unverified content",
            "provenance": {
                "record_type": "regulatory_evidence",
                "official_domain_validated": False,
            },
        },
        "sql",
        2,
    )

    assert ("regulatory", "NOTICE-1") in candidates
    assert ("regulatory", "NOTICE-2") not in candidates


def test_food_anchor_filter_preserves_regulatory_evidence():
    candidates = {
        ("food", "1"): {"source_type": "food", "source_id": "1"},
        ("regulatory", "NOTICE-1"): {
            "source_type": "regulatory",
            "source_id": "NOTICE-1",
        },
        ("food", "2"): {"source_type": "food", "source_id": "2"},
    }

    filtered = hybrid._filter_candidates_to_food_anchors(
        candidates, {"1"}
    )

    assert set(filtered) == {
        ("food", "1"),
        ("regulatory", "NOTICE-1"),
    }


def test_hybrid_retrieval_excludes_stale_regulatory_evidence():
    candidates = {}

    stale_provenance = {
        "record_type": "regulatory_evidence",
        "official_domain_validated": True,
        "authority": "FSSAI",
        "jurisdiction": "India",
        "source_url": "https://www.fssai.gov.in/notice",
        "document_type": "guidance",
        "document_status": "active",
        "published_at": "2025-01-01T00:00:00+00:00",
        "last_checked_at": "2026-01-01T00:00:00+00:00",
    }

    hybrid._merge_candidate(
        candidates,
        {
            "source_type": "regulatory",
            "source_id": "STALE-NOTICE",
            "title": "Stale guidance",
            "content": "Old regulatory guidance",
            "provenance": stale_provenance,
        },
        "sql",
        1,
    )

    assert ("regulatory", "STALE-NOTICE") not in candidates
