"""Kiểm thử chốt ngữ nghĩa bằng output giả lập, không gọi provider."""
import pytest

from app.models.models import Item
from app.pipeline import decision_verifier as verifier
from app.schemas.schemas import CuratorDecision, CuratorResult, ExtractedIdea, IdeaExtractionResult


def fixtures():
    item = Item(id="thread", name="Cuộn chỉ", description="Sợi chỉ quấn quanh lõi nhỏ.")
    idea = ExtractedIdea(original="châm cứu", normalized="châm cứu", status="VALID",
                         uses_target_object=True, object_used="Cuộn chỉ", target_object_role="kim",
                         inferred_signature_fields=["object_role", "mechanism"])
    decision = CuratorDecision(idea_index=0, decision="CREATE_NEW", confidence=.95,
                              code_name="Kim châm cứu", code_relation="DIFFERENT")
    candidate = {"id": "known", "name": "Khâu nối", "description": "Sợi chỉ nối vải"}
    return item, IdeaExtractionResult(ideas=[idea]), CuratorResult(decisions=[decision]), {0: [candidate]}


def check(*, grounded=True, relation="DIFFERENT"):
    return {"checks": [{"idea_index": 0, "source_text": "châm cứu", "grounded": grounded,
                        "evidence": "châm cứu", "reason": "Không được tự bổ sung kim vào cuộn chỉ.",
                        "comparisons": [{"code_id": "known", "relation": relation, "reason": "Đối chiếu chức năng."}]}]}


def execute(monkeypatch, payload, args=None):
    monkeypatch.setattr(verifier, "chat_json", lambda *a, **kw: (payload, {}))
    return verifier.verify_decisions(*(args or fixtures()), object())


def test_invented_component_stays_unassigned(monkeypatch):
    result, meta = execute(monkeypatch, check(grounded=False))
    assert result.decisions[0].decision == "UNCERTAIN"
    assert result.decisions[0].existing_code_id is None
    assert result.decisions[0].policy_gates["semantic_grounding_checked"] is False
    assert meta["runs"][0]["checks"]


def test_narrower_use_reuses_existing_category(monkeypatch):
    result, _ = execute(monkeypatch, check(relation="IDEA_NARROWER_THAN_CODE"))
    decision = result.decisions[0]
    assert decision.decision == "MATCH_EXISTING"
    assert decision.existing_code_id == "known"
    assert decision.pair_verified
    assert decision.existing_code_evaluations[0]["source"] == "DECISION_VERIFIER"


def test_distinct_grounded_function_can_create(monkeypatch):
    result, _ = execute(monkeypatch, check())
    assert result.decisions[0].decision == "CREATE_NEW"


@pytest.mark.parametrize("fault", ["source", "evidence", "foreign_code", "missing_code", "duplicate", "uncertain"])
def test_invalid_or_ambiguous_verdict_never_creates(monkeypatch, fault):
    payload = check()
    row = payload["checks"][0]
    if fault == "source": row["source_text"] = "câu khác"
    if fault == "evidence": row["evidence"] = "bằng chứng bịa"
    if fault == "foreign_code": row["comparisons"][0]["code_id"] = "foreign"
    if fault == "missing_code": row["comparisons"] = []
    if fault == "duplicate": payload["checks"].append(dict(row))
    if fault == "uncertain": row["comparisons"][0]["relation"] = "UNCERTAIN"
    result, _ = execute(monkeypatch, payload)
    assert result.decisions[0].decision == "UNCERTAIN"


def test_clear_match_does_not_add_call(monkeypatch):
    item, ideas, curator, candidates = fixtures()
    curator.decisions[0].decision = "MATCH_EXISTING"
    monkeypatch.setattr(verifier, "chat_json", lambda *a, **k: pytest.fail("Không được gọi thêm cho MATCH rõ"))
    result, meta = verifier.verify_decisions(item, ideas, curator, candidates, object())
    assert meta["skipped"] and result is curator


def test_fully_inferred_match_is_checked(monkeypatch):
    item, ideas, curator, candidates = fixtures()
    ideas.ideas[0].inferred_signature_fields = ["goal", "object_role", "mechanism"]
    curator.decisions[0].decision = "MATCH_EXISTING"
    curator.decisions[0].existing_code_id = "known"
    result, _ = execute(monkeypatch, check(grounded=False), (item, ideas, curator, candidates))
    assert result.decisions[0].decision == "UNCERTAIN"


def test_provider_failure_preserves_unresolved_idea(monkeypatch):
    def fail(*a, **kw):
        raise verifier.LLMJSONError("Provider không khả dụng")
    monkeypatch.setattr(verifier, "chat_json", fail)
    result, meta = verifier.verify_decisions(*fixtures(), object())
    assert result.decisions[0].decision == "UNCERTAIN"
    assert meta["runs"][0]["failed"]
