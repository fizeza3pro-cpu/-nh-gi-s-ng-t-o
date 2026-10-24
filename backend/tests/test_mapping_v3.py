"""Hồi quy ngân sách, resolver theo ngữ cảnh và gộp mã có thể truy vết."""
from contextlib import contextmanager
from copy import deepcopy
import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.models import Item, ItemCode, Participant, Response, ResponseIdea, ResponseScoringStatus, PipelineAudit
from app.pipeline import scope_audit
from app.pipeline.codebook_service import _merge_equivalent_codes
from app.pipeline.dynamic_mapping import _shared_candidate_payload
from app.pipeline.decision_verifier import verification_reason
from app.pipeline.llm import chat_json, collect_llm_calls, aggregate_usage, LLMJSONError
from app.schemas.schemas import CuratorDecision, CuratorResult, ExtractedIdea, IdeaExtractionResult, Item as ItemSchema
from app.controllers import response_worker, response_controller, admin_controller
from tests.fake_llm import FakeClient
import pytest


SIGNATURE = {"goal": "chứa đồ", "object_role": "vật chứa", "mechanism": "khoang rỗng"}


def database():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def test_catalog_deduplicates_definitions_but_keeps_per_idea_permissions():
    code = {"id": "a", "name": "Vật chứa", "retrieval_score": .8,
            "semantic_similarity": .9, "signature_similarity": {"weighted": .5}}
    payload = json.loads(_shared_candidate_payload([
        {"idea_index": 0, "nearest_codes": [code]},
        {"idea_index": 1, "nearest_codes": [code, {"id": "b", "name": "Mã riêng ý 1"}]},
    ]))
    assert len(payload["codes"]) == 2
    assert payload["ideas"][0]["candidates"] == [{"code_id": "a", "retrieval_score": .8}]
    assert [x["code_id"] for x in payload["ideas"][1]["candidates"]] == ["a", "b"]
    assert code["signature_similarity"] == {"weighted": .5}
    assert "signature_similarity" not in payload["codes"][0]


def test_distinct_creation_skips_verifier_but_close_creation_is_checked():
    idea = ExtractedIdea(original="chứa đồ", normalized="chứa đồ", status="VALID")
    decision = CuratorDecision(idea_index=0, decision="CREATE_NEW", confidence=.9)
    assert verification_reason(idea, decision, []) is None
    assert verification_reason(idea, decision, [{"semantic_similarity": .9, "signature_similarity": {"weighted": .5}}])
    decision.pair_verified = True
    idea.inferred_signature_fields = ["goal", "object_role", "mechanism"]
    assert verification_reason(idea, decision, []) is None


def test_usage_counts_requests_once_even_when_checkpoint_and_wrappers_repeat():
    payload = {"content": '{"ok":true}', "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    _, first = chat_json(FakeClient([payload]), model="test", temperature=0, prompt="p", stage="idea_extraction")
    _, second = chat_json(FakeClient([payload]), model="test", temperature=0, prompt="p", stage="code_curator")
    calls = collect_llm_calls({"runs": [first, second], "checkpoint": deepcopy(first), "usage": {"total_tokens": 9999}})
    assert len(calls) == 2
    assert aggregate_usage(calls)["total_tokens"] == 30
    assert all(c["usage_known"] for c in calls)


def test_truncation_recovery_is_bounded_and_keeps_failed_usage():
    client = FakeClient([{"content": '{"incomplete":', "finish_reason": "length", "usage": {"total_tokens": 20}}])
    with pytest.raises(LLMJSONError) as caught:
        chat_json(client, model="test", temperature=0, prompt="p", stage="idea_extraction", max_tokens=512, max_retries=3)
    assert client.chat.completions.calls == 2
    assert caught.value.metadata["usage"]["total_tokens"] == 40
    assert len(collect_llm_calls(caught.value.metadata)) == 2


def test_semantic_contract_failures_keep_usage(monkeypatch):
    from app.pipeline.semantic_verifier import verify_pair, propose_scope
    from app.pipeline.dynamic_mapping import _reconcile_new_code_batch
    item = ItemSchema(id="bag", name="Balo", description="Khoang chứa")
    code = {"id": "a", "name": "Chứa đồ", "functional_signature": SIGNATURE}
    for function in (verify_pair, propose_scope):
        client = FakeClient([{"content": '{}', "usage": {"total_tokens": 50}}])
        with pytest.raises(LLMJSONError) as caught:
            function(item, "đựng đồ", code, client)
        assert aggregate_usage(collect_llm_calls(caught.value.metadata))["total_tokens"] == 50
    ideas = IdeaExtractionResult(ideas=[ExtractedIdea(original=text, normalized=text, status="VALID")
                                       for text in ("đựng sách", "đựng quần áo")])
    curator = CuratorResult(decisions=[CuratorDecision(idea_index=i, decision="CREATE_NEW",
                       functional_signature=SIGNATURE, confidence=.9) for i in (0, 1)])
    _, meta = _reconcile_new_code_batch(item=item, ideas=ideas, curator=curator,
        client=FakeClient([{"content": '{"groups":[{}]}', "usage": {"total_tokens": 70}}]))
    assert aggregate_usage(collect_llm_calls(meta))["total_tokens"] == 70
    @contextmanager
    def factory():
        yield None
    monkeypatch.setattr(scope_audit, "member_rows", lambda db, ids: [])
    expansion = CuratorResult(decisions=[CuratorDecision(idea_index=0, decision="EXPAND_EXISTING",
                         existing_code_id="a", functional_signature=SIGNATURE, confidence=.9)])
    _, audits, _ = scope_audit.verify_expansions(factory, item, ideas, expansion, [],
        FakeClient([{"content": '{"checks":[{}]}', "usage": {"total_tokens": 60}}]))
    assert audits[-1]["outcome"] == "TECHNICAL_ERROR"
    assert aggregate_usage(collect_llm_calls(audits))["total_tokens"] == 60


def test_merging_can_keep_neighbor_overlap_without_claiming_scope_expansion(monkeypatch):
    @contextmanager
    def factory():
        yield None
    monkeypatch.setattr(scope_audit, "member_rows", lambda db, ids: [("old", "đựng sách")])
    sources = ["đựng sách", "đựng đồ", "đựng dụng cụ"]
    checks = [{"source_text": text, "relation": "SAME_CATEGORY", "goal_match": True,
               "role_match": True, "exclusion_hit": False, "evidence": text, "reason": "Cùng chức năng"} for text in sources]
    decision = CuratorDecision(idea_index=0, decision="MATCH_EXISTING", existing_code_id="a",
                              absorbed_code_ids=["b"], functional_signature=SIGNATURE, confidence=.9)
    result, audit, guards = scope_audit.verify_expansions(factory, ItemSchema(id="bag", name="Balo", description="Khoang chứa"),
        IdeaExtractionResult(ideas=[ExtractedIdea(original=sources[1], normalized=sources[1], status="VALID")]),
        CuratorResult(decisions=[decision]), [{"id": "c", "positive_examples": [sources[2]], "functional_signature": SIGNATURE}],
        FakeClient([json.dumps({"checks": checks})]), merging=True)
    assert result.decisions[0].decision == "MATCH_EXISTING" and guards
    assert audit[-1] == {"operation": "MERGE_EQUIVALENT", "outcome": "OVERLAP_DETECTED", "code_ids": ["c"]}


def test_merge_records_exact_transfers_keeps_definition_vector_and_final_snapshot():
    engine = database()
    with Session(engine) as db:
        item = Item(id="bag", name="Balo")
        db.add_all([item, Participant(id="p")])
        for key in ("a", "b"):
            db.add(ItemCode(id=key, item_id="bag", name=key, normalized_name=key,
                           functional_signature=SIGNATURE, embedding=[1., 0.], embedding_model="v1"))
        frozen = {"score_policy": "FINAL_FROZEN_V1", "mapping_snapshot": {"ideas": [{"code": "b"}]}}
        row = Response(id="r", participant_id="p", item_id="bag", raw_input="đựng đồ", mapping={},
                       scoring_status=ResponseScoringStatus.FINAL, scoring_meta=deepcopy(frozen), fluency=1)
        db.add(row)
        db.add(ResponseIdea(id="i", response_id="r", code_id="b", original="đựng đồ", normalized="đựng đồ", mapping_status="VALID"))
        db.commit()
        target, source = db.get(ItemCode, "a"), db.get(ItemCode, "b")
        moved = _merge_equivalent_codes(db, item=item, source=source, target=target, reason="Cùng chức năng")
        db.commit()
        assert moved == [{"idea_id": "i", "response_id": "r", "from_code_id": "b", "to_code_id": "a"}]
        assert row.scoring_meta == frozen and row.fluency == 1
        assert target.functional_signature == SIGNATURE and target.embedding_model == "v1" and target.embedding == [1., 0.]
        assert target.scope_revision == 0
        history = admin_controller.code_history(db, "bag", "a", 1, 5)
        assert history["entries"][0]["operation"] == "MERGE_EQUIVALENT"
        assert history["entries"][0]["previous"] == history["entries"][0]["current"]
        assert history["entries"][0]["moved_ideas"] == moved


def test_resolver_ignores_centroid_and_unrelated_changes_but_wakes_for_scope(monkeypatch):
    engine = database()
    monkeypatch.setattr(response_worker, "SessionLocal", lambda: Session(engine))
    with Session(engine) as db:
        item = Item(id="bag", name="Balo")
        code = ItemCode(id="a", item_id="bag", name="Vật chứa", normalized_name="vat chua", functional_signature=SIGNATURE)
        row = Response(id="r", participant_id="p", item_id="bag", raw_input="đựng đồ", mapping={},
                       processing_state="DONE", scoring_status=ResponseScoringStatus.PENDING_REVIEW, resolution_epoch=0)
        db.add_all([item, Participant(id="p"), code, row])
        db.add(ResponseIdea(id="i", response_id="r", original="đựng đồ", normalized="đựng đồ", mapping_status="VALID", functional_signature=SIGNATURE))
        db.commit()
        context = response_worker._resolution_context(db, row, response_worker.list_curator_codes(db, "bag"))
        row.mapping_checkpoint = {"resolution_context": context}
        item.codebook_epoch = 1
        code.centroid = [1., 0.]
        db.add(ItemCode(id="other", item_id="bag", name="Nhiên liệu", normalized_name="fuel",
                       functional_signature={"goal": "đốt", "object_role": "nhiên liệu", "mechanism": "cháy"}))
        db.commit()
        assert not response_worker._wake_one_unresolved()
        assert response_worker._claim("resolution") is None
        db.expire_all()
        code.scope_revision += 1
        item.codebook_epoch = 2
        db.commit()
        assert response_worker._wake_one_unresolved()
        db.expire_all()
        assert row.resolution_next_at is not None
        assert response_worker._claim("resolution") is not None


def test_waiting_admin_does_not_keep_frontend_polling():
    engine = database()
    with Session(engine) as db:
        db.add_all([Item(id="bag", name="Balo"), Participant(id="p")])
        row = Response(participant_id="p", item_id="bag", raw_input="ý mơ hồ", mapping={},
                       processing_state="DONE", scoring_status=ResponseScoringStatus.PENDING_REVIEW)
        db.add(row); db.commit()
        result = response_controller._to_response(row)
        assert result.result_state == "REVIEW" and not result.needs_processing


def test_cleanup_json_requires_backup_and_preserves_final_and_elaboration(tmp_path):
    from scripts.cleanup_mapping_contract import cleanup
    engine = database()
    with Session(engine) as db:
        db.add_all([Item(id="bag", name="Balo"), Participant(id="p"),
                    ItemCode(id="a", item_id="bag", name="A", normalized_name="a",
                             functional_signature={**SIGNATURE, "target": "sách", "context": "lớp", "transformation": ""})])
        for key, status in [("final", ResponseScoringStatus.FINAL), ("pending", ResponseScoringStatus.PENDING_REVIEW)]:
            db.add(Response(id=key, item_id="bag", participant_id="p", raw_input="đựng sách", mapping={},
                            processing_state="DONE", scoring_status=status, scoring_meta={"mapping_snapshot": {"immutable": True}}))
            db.add(ResponseIdea(id=key, response_id=key, original="đựng sách", normalized="đựng sách", mapping_status="VALID",
                functional_signature={**SIGNATURE, "target": "sách"}, mapping_evidence={
                    "uses_target_object": True, "elaboration_details": {"target": "sách", "context": "lớp"}}))
        db.commit()
        frozen = deepcopy(db.get(ResponseIdea, "final").functional_signature)
        summary = cleanup(db)
        assert not summary["applied"] and summary["codes"] == 1 and summary["ideas"] == 1
        assert "target" in db.get(ItemCode, "a").functional_signature
        backup = tmp_path / "backup.json"
        cleanup(db, apply=True, backup_path=backup)
        db.commit()
        assert db.get(ResponseIdea, "final").functional_signature == frozen
        assert db.get(ResponseIdea, "pending").functional_signature == SIGNATURE
        evidence = db.get(ResponseIdea, "pending").mapping_evidence
        assert "uses_target_object" not in evidence
        assert evidence["elaboration_details"] == {"target": "sách", "context": "lớp"}
        assert json.loads(backup.read_text(encoding="utf-8"))["changes"]


def test_admin_neighbors_history_and_usage_are_bounded_and_distinguish_background():
    engine = database()
    with Session(engine) as db:
        db.add_all([Item(id="bag", name="Balo"), Item(id="other", name="Khác"), Participant(id="p")])
        for key, item in [("a", "bag"), ("b", "bag"), ("foreign", "other")]:
            db.add(ItemCode(id=key, item_id=item, name=key, normalized_name=key,
                           functional_signature=SIGNATURE, embedding=[1., 0.], embedding_model="v1",
                           scope_history=[{"change": "old"}] * 12 if key == "a" else []))
        db.add(Response(id="r", item_id="bag", participant_id="p", raw_input="đựng đồ", mapping={}))
        client = FakeClient([{"content": '{"ok":true}', "usage": {"total_tokens": 50}}])
        _, meta = chat_json(client, model="test", temperature=0, prompt="p", stage="code_curator")
        db.add_all([PipelineAudit(id="job", item_id="bag", response_id="r", event="PIPELINE_ATTEMPT", payload=meta),
                    PipelineAudit(id="bg", item_id="bag", event="AUTO_CODE_AUDIT", payload=deepcopy(meta))])
        db.commit()
        assert [r["code_id"] for r in admin_controller.code_neighbors(db, "bag", "a", 1)] == ["b"]
        history = admin_controller.code_history(db, "bag", "a", 1, 3)
        assert len(history["entries"]) == 3 and history["total"] == 12
        assert "moved_ideas" not in history["entries"][0]
        audit = admin_controller.pipeline_audits(db, "bag", 2)
        assert {r["usage_scope"] for r in audit} == {"response_lifecycle", "background_event"}
        assert all(r["usage_summary"]["total_tokens"] == 50 for r in audit)
