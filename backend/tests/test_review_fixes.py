"""Hồi quy rà soát 07/11/2026: ý treo, nhãn lỗi kỹ thuật, phạm vi cũ, retry và bằng chứng trùng."""
import json
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.controllers import response_worker
from app.db import Base
from app.models.models import Item, ItemCode, Participant, PipelineAudit, Response, ResponseIdea
from app.pipeline import adjudication as judge
from app.pipeline import dynamic_mapping
from app.pipeline.codebook_service import persist_mapping
from app.pipeline.dynamic_mapping import _normalize_curator_contract, run_code_mapping
from app.pipeline.llm import LLMJSONError, chat_json
from app.pipeline.scoring import run_scoring
from app.schemas.schemas import (CuratorDecision, CuratorResult, ExtractedIdea, FunctionalSignature,
                                 IdeaExtractionResult, MappingResult, PerIdeaScore)
from tests.fake_llm import FakeClient
from tests.test_decision_verifier import ITEM, SIG, final, fixture
from tests.test_dynamic_codebook import _engine, _response
from tests.test_scoring import ITEM as DUA


def _persist_fixture():
    engine = _engine()
    Base.metadata.create_all(engine)
    db = Session(engine)
    participant = Participant(id=str(uuid.uuid4()))
    item = Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại")
    response = _response(participant.id, item.id)
    db.add_all([participant, item, response])
    db.flush()
    return db, item, response


def test_missing_curator_decision_is_labeled_for_admin_not_as_semantic_ambiguity():
    db, item, response = _persist_fixture()
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(original="kê bàn", normalized="kê bàn", status="VALID",
                                                           object_used="Vỏ đạn", functional_signature=SIG)])
    _, uncertain = persist_mapping(db, item=item, response=response, extraction=extraction,
                                   curator=CuratorResult(decisions=[]))
    idea = response.ideas[0]
    assert uncertain and idea.curator_decision == "MISSING_DECISION"
    assert idea.review_payload["issue_type"] == "MISSING_DECISION"
    assert db.scalar(select(PipelineAudit).where(PipelineAudit.event == "CURATOR_MISSING_DECISION")) is not None


def test_match_to_code_absorbed_in_same_pass_is_held_as_stale_scope():
    db, item, response = _persist_fixture()
    rules = dict(inclusion_rules=["Vỏ đạn được xâu nối thành đồ trang sức đeo trên cơ thể"],
                 exclusion_rules=["Không gồm đồ trang trí treo tường không đeo trên người"])
    target = ItemCode(item_id=item.id, name="Vỏ đạn làm vòng cổ", normalized_name="vong co",
                      description="Vòng cổ Vỏ đạn.", functional_signature=dict(SIG),
                      positive_examples=["vòng cổ"], **rules)
    absorbed = ItemCode(item_id=item.id, name="Vỏ đạn làm vòng tay", normalized_name="vong tay",
                        description="Vòng tay Vỏ đạn.", functional_signature=dict(SIG),
                        positive_examples=["vòng tay"], **rules)
    db.add_all([target, absorbed])
    db.flush()
    signature = FunctionalSignature(goal="trang trí cơ thể", object_role="hạt xâu", mechanism="xâu nối")
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(original=text, normalized=text, status="VALID",
        object_used="Vỏ đạn", functional_signature=signature) for text in ("làm trang sức", "xâu vòng tay")])
    expand = CuratorDecision(idea_index=0, decision="EXPAND_EXISTING", code_relation="IDEA_BROADER_THAN_CODE",
        existing_code_id=target.id, absorbed_code_ids=[absorbed.id], code_name="Vỏ đạn làm trang sức",
        code_description="Xâu Vỏ đạn thành trang sức đeo.", functional_signature=signature,
        scope_variants=["xâu vỏ đạn làm lắc chân", "xâu vỏ đạn làm dây chuyền"], positive_examples=["làm trang sức"],
        existing_code_evaluations=[{"code_id": target.id, "relation": "IDEA_BROADER_THAN_CODE"},
                                   {"code_id": absorbed.id, "relation": "IDEA_BROADER_THAN_CODE"}],
        reviewed_by_challenger=True, confidence=.9, **rules)
    match = CuratorDecision(idea_index=1, decision="MATCH_EXISTING", existing_code_id=absorbed.id,
                            code_relation="SAME_CATEGORY", pair_verified=True, confidence=.9)
    persist_mapping(db, item=item, response=response, extraction=extraction,
                    curator=CuratorResult(decisions=[expand, match]),
                    code_snapshots=[{"id": target.id, "scope_revision": 0}, {"id": absorbed.id, "scope_revision": 0}])
    held = [idea for idea in response.ideas if idea.line_index == 1][0]
    assert absorbed.maturity_status.value == "MERGED"
    assert held.review_payload["issue_type"] == "STALE_SCOPE" and held.code_id is None


def test_worker_schedules_stale_scope_for_quick_rerun(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = lambda: Session(engine)
    monkeypatch.setattr(response_worker, "SessionLocal", factory)
    monkeypatch.setattr(response_worker.settings, "mock_mode", False)
    monkeypatch.setattr(response_worker, "chat_client", lambda: object())
    monkeypatch.setattr(response_worker, "make_embedding_client", lambda: None)
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(original="kê bàn", normalized="kê bàn", status="VALID",
                                                           object_used="Balo", functional_signature=SIG)])
    monkeypatch.setattr(response_worker, "run_idea_extraction", lambda *a, **kw: (extraction, {}))
    monkeypatch.setattr(response_worker, "run_code_mapping", lambda *a, **kw: (CuratorResult(decisions=[]), {}))

    def fake_persist(db, *, response, **kwargs):
        db.add(ResponseIdea(response_id=response.id, original="kê bàn", normalized="kê bàn", line_index=0,
                            mapping_status="VALID", review_status="PENDING",
                            review_payload={"issue_type": "STALE_SCOPE"}))
        db.flush()
        return MappingResult(ideas=[]), True
    monkeypatch.setattr(response_worker, "persist_mapping", fake_persist)
    with factory() as db:
        db.add_all([Item(id="bag", name="Balo"), Participant(id="p")])
        db.add(Response(id="r", item_id="bag", participant_id="p", raw_input="kê bàn", input_lines=["kê bàn"],
                        mapping={}, scoring={}, processing_state="RUNNING", processing_claim_token="t"))
        db.commit()
    response_worker._run_mapping("r", "t")
    with factory() as db:
        row = db.get(Response, "r")
        assert row.resolution_next_at is not None and row.mapping_checkpoint["technical_retry_indices"] == [0]
        assert row.ideas[0].coding_state == "RESOLVING"


def test_invalid_json_retry_raises_temperature_from_zero():
    client = FakeClient([{"content": '{"a":', "usage": {"total_tokens": 5}}, '{"a":1}'])
    data, meta = chat_json(client, model="test", temperature=0, prompt="p", stage="scoring", max_retries=1)
    temperatures = [request["temperature"] for request in client.chat.completions.requests]
    assert data == {"a": 1} and temperatures == [0, 0.2]
    assert "retry_temperature_after_invalid_json" in meta["request_fallbacks"]


def test_curator_batch_failure_is_halved_not_fanned_out(monkeypatch):
    ideas, _, candidates = fixture(4)
    monkeypatch.setattr(dynamic_mapping, "rank_code_candidates", lambda *a, **kw: candidates)
    monkeypatch.setattr(dynamic_mapping, "run_code_challenger", lambda item, ideas, cand, curator, *a: (curator, {}))
    stages = []

    def reply(*args, **kwargs):
        stages.append(kwargs["stage"])
        if len(stages) == 1:
            raise LLMJSONError("JSON hỏng", metadata={"error_type": "LLMJSONError", "error_category": "LLM_ERROR"})
        indices = [index for index in range(4) if f'"idea_index":{index}' in kwargs["prompt"]]
        return {"decisions": [final(index) for index in indices]}, {}
    monkeypatch.setattr(dynamic_mapping, "chat_json", reply)
    result, meta = run_code_mapping(ITEM, ideas, candidates[0], object())
    assert stages == ["code_curator"] * 3 and meta["split_reason"] == "curator_failure"
    assert sorted(decision.idea_index for decision in result.decisions) == [0, 1, 2, 3]


def test_challenger_receives_relabeled_curator_comparisons(monkeypatch):
    ideas, _, candidates = fixture()
    row = final()
    row.pop("source_text")
    row["comparisons"][0].update(relation="IDEA_BROADER_THAN_CODE", goal_match=False, role_match=False)
    checked = _normalize_curator_contract(CuratorResult(decisions=[CuratorDecision.model_validate(row)]),
                                          ideas, candidates)
    prompts = []

    def reply(*args, **kwargs):
        prompts.append(kwargs["prompt"])
        return {"decisions": [final()]}, {}
    monkeypatch.setattr(judge, "chat_json", reply)
    judge.adjudicate_decisions(ITEM, ideas, checked, candidates, object())
    data = prompts[0].split("Dữ liệu:")[-1]
    assert '"curator_comparisons"' in data and "IDEA_BROADER_THAN_CODE" not in data


def test_same_evidence_is_counted_for_one_facet_only():
    idea = PerIdeaScore(idea_id="a", original="kê chân bàn trong bếp", normalized="kê bàn", code="KÊ",
                        originality=0, elaboration=1)
    flat = json.dumps({"elaboration_analysis": [{"idea_id": "a", "target": "trong bếp", "mechanism": "",
                       "context": "trong bếp", "goal": ""}]}, ensure_ascii=False)
    result, _ = run_scoring(DUA, 1, 1, ["KÊ"], [idea], FakeClient([flat, flat, flat, "{}"]), runs=3)
    assert result.per_idea_scores[0].elaboration == 2
    assert list(result.per_idea_scores[0].elaboration_details) == ["target"]
