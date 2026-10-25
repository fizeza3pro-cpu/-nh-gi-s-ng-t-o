"""Hồi quy bốn kênh vector, cache, centroid khác phiên bản và cổng MATCH."""
from copy import deepcopy
from types import SimpleNamespace
import json
import math

import pytest

from app.config import settings
from app.pipeline import code_retrieval as retrieval
from app.pipeline import embedding
from app.pipeline.centroid import rebuild_confirmed_members
from app.pipeline.dynamic_mapping import _normalize_curator_contract, _finalize_curator
from app.pipeline.codebook_service import _stored_match_review_reason
from app.models.models import ItemCode
from app.schemas.schemas import ExtractedIdea, IdeaExtractionResult, CuratorResult, CuratorDecision, Item
from tests.fake_llm import FakeClient

SIG = {"goal": "cố định giấy", "object_role": "vật chặn", "mechanism": "trọng lượng"}


def fixture_vectors(monkeypatch):
    requests = []
    vectors = {"giữ giấy khỏi bay": [1., 0.], "đốt": [0., 1.],
               "Chặn giấy Giữ giấy cố định": [.8, .6],
               "Nhiên liệu Đốt để sưởi": [.9, math.sqrt(.19)],
               "Mục đích: giữ giấy khỏi bay": [1., 0.], "Mục đích: cố định giấy": [1., 0.],
               "Mục đích: tạo nhiệt": [0., 1.], "Vai trò của vật: vật chặn": [1., 0.],
               "Vai trò của vật: nhiên liệu": [0., 1.], "Cơ chế: trọng lượng": [1., 0.],
               "Cơ chế: cháy": [0., 1.]}
    def embed(texts, client):
        requests.append(list(texts))
        return embedding.EmbeddingBatch([vectors.get(text, [1., 0.]) for text in texts], "test::raw-fields-v3", True)
    monkeypatch.setattr(retrieval, "embed_texts", embed)
    monkeypatch.setattr(retrieval, "embedding_model", lambda client: "test::raw-fields-v3")
    monkeypatch.setattr(settings, "retrieval_raw_weight", .5)
    return requests


def ideas():
    return IdeaExtractionResult(ideas=[ExtractedIdea(original="giữ giấy khỏi bay", normalized="giữ giấy", status="VALID",
        object_used="Gạch", functional_signature={**SIG, "goal": "giữ giấy khỏi bay"})])


def codes():
    return [{"id": "keep", "name": "Chặn giấy", "description": "Giữ giấy cố định", "functional_signature": SIG},
            {"id": "burn", "name": "Nhiên liệu", "description": "Đốt để sưởi",
             "functional_signature": {"goal": "tạo nhiệt", "object_role": "nhiên liệu", "mechanism": "cháy"}}]


def test_separate_semantic_fields_can_outweigh_wrong_raw_neighbor(monkeypatch):
    calls = fixture_vectors(monkeypatch)
    data, pool = ideas(), codes()
    ranked = retrieval.rank_code_candidates(data, pool, limit=1)[0]
    assert ranked[0]["id"] == "keep"  # Raw đơn thuần cố ý gần mã sai hơn trong fixture.
    assert ranked[0]["signature_similarity"]["goal"] == 1
    assert ranked[0]["lexical_similarity"]["goal"] < 1
    assert ranked[0]["retrieval_score"] == pytest.approx(.9)
    assert data.ideas[0].embedding == [1., 0.]
    assert "giữ giấy khỏi bay" in calls[0]
    assert "Mục đích: giữ giấy khỏi bay" in calls[0]
    assert not any("\n" in text for text in calls[0])
    assert "signature_embeddings" not in ranked[0] and "embedding" not in ranked[0]


def test_code_cache_reused_and_invalidated_by_scope_or_model(monkeypatch):
    calls = fixture_vectors(monkeypatch)
    pool = codes()
    retrieval.rank_code_candidates(ideas(), pool)
    old = deepcopy(pool[0]["signature_embeddings"])
    retrieval.rank_code_candidates(ideas(), pool)
    assert "Chặn giấy Giữ giấy cố định" not in calls[1]
    pool[0]["description"] = "Định nghĩa mới"
    retrieval.rank_code_candidates(ideas(), pool)
    assert "Chặn giấy Định nghĩa mới" in calls[2]
    assert pool[0]["signature_embeddings"]["digest"] != old["digest"]
    pool[0]["signature_embeddings"]["model"] = "legacy"
    retrieval.rank_code_candidates(ideas(), pool)
    assert "Chặn giấy Định nghĩa mới" in calls[3]


def test_raw_centroid_must_match_representation_and_not_be_dirty(monkeypatch):
    fixture_vectors(monkeypatch)
    monkeypatch.setattr(settings, "centroid_retrieval_enabled", True)
    pool = codes()[:1]
    pool[0].update(centroid=[1., 0.], centroid_model="test::core-function-v2", centroid_dirty=False)
    assert retrieval.rank_code_candidates(ideas(), pool)[0][0]["centroid_similarity"] is None
    pool[0]["centroid_model"] = "test::raw-fields-v3"
    assert retrieval.rank_code_candidates(ideas(), pool)[0][0]["centroid_similarity"] == 1
    pool[0]["centroid_dirty"] = True
    assert retrieval.rank_code_candidates(ideas(), pool)[0][0]["centroid_similarity"] is None


def test_missing_fields_are_not_embedded_or_renormalized_to_perfect_score(monkeypatch):
    calls = fixture_vectors(monkeypatch)
    data, pool = ideas(), codes()[:1]
    data.ideas[0].functional_signature.object_role = ""
    data.ideas[0].functional_signature.mechanism = ""
    row = retrieval.rank_code_candidates(data, pool)[0][0]
    assert row["signature_similarity"] == {"goal": 1., "object_role": 0., "mechanism": 0., "weighted": .4}
    assert "Vai trò của vật: " not in calls[0] and "Cơ chế: " not in calls[0]


def test_raw_profile_match_cannot_persist_without_independent_verification(monkeypatch):
    fixture_vectors(monkeypatch)
    data, pool = ideas(), codes()[:1]
    candidates = retrieval.rank_code_candidates(data, pool)
    curator = CuratorResult(decisions=[CuratorDecision(idea_index=0, decision="MATCH_EXISTING",
                        existing_code_id="keep", code_relation="SAME_CATEGORY", confidence=.99)])
    normalized = _normalize_curator_contract(curator, data, candidates)
    assert _stored_match_review_reason(data.ideas[0], normalized.decisions[0])
    client = FakeClient([json.dumps({"checks": [{"idea_index": 0, "source_text": data.ideas[0].original,
        "grounded": True, "evidence": "giấy", "reason": "Chức năng có trong câu nguồn",
        "comparisons": [{"code_id": "keep", "relation": "SAME_CATEGORY", "reason": "Cố định giấy"}]}]}, ensure_ascii=False)])
    final, meta = _finalize_curator(Item(id="brick", name="Gạch", description="Vật nặng"), data, normalized,
                                  candidates, client, None)
    assert final.decisions[0].pair_verified
    assert _stored_match_review_reason(data.ideas[0], final.decisions[0]) is None
    assert meta["triggers"] == {0: "multi_vector_match_requires_semantic_check"}


def test_centroid_switches_representation_and_disables_partial_legacy_mix():
    code = ItemCode(item_id="a", name="A", normalized_name="a", centroid=[0., 1.], centroid_count=1,
                    centroid_model="old", centroid_revision=1, drift_flag=False)
    rebuild_confirmed_members(code, [([1., 0.], "new"), ([0., 1.], "old")], expected_model="new", drift_cosine_floor=.7)
    assert code.centroid_model == "new" and code.centroid == [1., 0.] and code.drift_flag
    rebuild_confirmed_members(code, [([1., 0.], "new")], expected_model="new", drift_cosine_floor=.7)
    assert not code.drift_flag


def test_embedding_batch_rejects_duplicate_indices_without_misalignment(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "cloudflare")
    monkeypatch.setattr(embedding.time, "sleep", lambda seconds: None)
    count = 0
    def create(**kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[1., 0.]), SimpleNamespace(index=0, embedding=[0., 1.])])
        return SimpleNamespace(data=[SimpleNamespace(index=1, embedding=[0., 2.]), SimpleNamespace(index=0, embedding=[2., 0.])])
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    batch = embedding.embed_texts(["câu A", "câu B"], client)
    assert batch.vectors == [[1., 0.], [0., 1.]] and count == 2


def test_later_invalid_vector_does_not_leave_partial_results_on_retry(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "cloudflare")
    monkeypatch.setattr(embedding.time, "sleep", lambda seconds: None)
    count = 0
    def create(**kwargs):
        nonlocal count
        count += 1
        values = [[1., 0.], [0., 0.]] if count == 1 else [[0., 1.], [1., 0.]]
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=value) for i, value in enumerate(values)])
    result = embedding.embed_texts(["A", "B"], SimpleNamespace(embeddings=SimpleNamespace(create=create)))
    assert result.vectors == [[0., 1.], [1., 0.]] and count == 2


def test_new_field_similarity_does_not_reuse_legacy_lexical_risk_floor():
    from app.pipeline.decision_verifier import verification_reason
    idea = ideas().ideas[0]
    decision = CuratorDecision(idea_index=0, decision="CREATE_NEW", confidence=.9)
    candidate = {"retrieval_profile": retrieval.RETRIEVAL_PROFILE, "semantic_similarity": .8,
                 "signature_similarity": {"goal": .3, "object_role": .3, "mechanism": .9, "weighted": .48}}
    assert verification_reason(idea, decision, [candidate]) is None
    candidate["signature_similarity"].update(goal=.8, object_role=.8)
    assert verification_reason(idea, decision, [candidate]) == "new_code_overlaps_semantic_fields"
