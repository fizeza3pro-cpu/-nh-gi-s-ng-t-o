"""Hồi quy phân xử cuối: căn cứ, ứng viên, cô lập lỗi và số lần gọi."""
from copy import deepcopy
import json

import pytest

from app.pipeline import adjudication as judge
from app.pipeline.dynamic_mapping import run_code_mapping, _finalize_curator, _stored_match_review_reason
from app.pipeline.code_retrieval import RETRIEVAL_PROFILE, select_diverse_candidates
from app.schemas.schemas import CuratorDecision, CuratorResult, ExtractedIdea, IdeaExtractionResult, Item
from tests.fake_llm import FakeClient


SIG = {"goal": "kê đỡ", "object_role": "vật kê", "mechanism": "chịu lực"}
ITEM = Item(id="shell", name="Vỏ đạn", description="Vỏ kim loại rỗng.")


def fixture(count=1):
    ideas = IdeaExtractionResult(ideas=[ExtractedIdea(original="chân chèn bàn ghế", normalized="kê bàn",
        status="VALID", functional_signature=SIG) for _ in range(count)])
    codes = [
        {"id": "block", "name": "Chặn vật", "description": "Ngăn dịch chuyển", "retrieval_score": .8,
         "retrieval_profile": RETRIEVAL_PROFILE, "functional_signature": SIG, "exclusion_rules": []},
        {"id": "support", "name": "Kê đỡ", "description": "Kê/chèn chân bàn ghế", "retrieval_score": .6,
         "retrieval_profile": RETRIEVAL_PROFILE, "functional_signature": SIG,
         "exclusion_rules": ["Không gồm dùng làm vật ném"]},
    ]
    source = CuratorResult(decisions=[CuratorDecision(idea_index=i, decision="UNCERTAIN",
        confidence=.5, reason="Cần phân biệt chặn với kê đỡ") for i in range(count)])
    return ideas, source, {i: deepcopy(codes) for i in range(count)}


def final(index=0, **changes):
    row = {
        "idea_index": index, "source_text": "chân chèn bàn ghế", "grounded": True,
        "evidence": "chèn bàn ghế", "decision": "MATCH_EXISTING", "existing_code_id": "support",
        "code_relation": "IDEA_NARROWER_THAN_CODE", "confidence": .9,
        "reason": "Đồ vật trong ngữ cảnh dùng làm vật kê/chèn.",
        "comparisons": [
            {"code_id": "block", "relation": "DIFFERENT", "goal_match": False, "role_match": False,
             "reason": "Ngăn dịch chuyển khác kê đỡ."},
            {"code_id": "support", "relation": "IDEA_NARROWER_THAN_CODE", "goal_match": True,
             "role_match": True, "reason": "Kê/chèn chân bàn nằm trong phạm vi."},
        ],
    }
    row.update(changes)
    return row


def execute(monkeypatch, payload, count=1):
    calls = []
    def reply(*args, **kwargs):
        calls.append(kwargs)
        return deepcopy(payload), {}
    monkeypatch.setattr(judge, "chat_json", reply)
    ideas, source, candidates = fixture(count)
    result, meta = judge.adjudicate_decisions(ITEM, ideas, source, candidates, object())
    return result, meta, calls


def test_rank_two_match_is_final_without_another_verifier(monkeypatch):
    ideas, source, candidates = fixture()
    client = FakeClient([json.dumps({"decisions": [final()]}, ensure_ascii=False)])
    result, meta = judge.adjudicate_decisions(ITEM, ideas, source, candidates, client)
    decision = result.decisions[0]
    assert client.chat.completions.calls == 1
    assert decision.pair_verified and decision.reviewed_by_challenger
    assert decision.existing_code_id == "support"
    result, _ = _finalize_curator(ITEM, ideas, result, candidates, client, None)
    assert client.chat.completions.calls == 1
    assert _stored_match_review_reason(ideas.ideas[0], result.decisions[0]) is None
    assert meta["runs"][0]["checks"][0]["outcome"] == "ACCEPTED"


@pytest.mark.parametrize("fault", ["source", "evidence", "foreign_id", "missing_code", "duplicate", "fake_exclusion", "false_goal", "wrong_relation", "merge"])
def test_bad_contract_or_inconsistent_match_is_not_accepted(monkeypatch, fault):
    row = final()
    if fault == "source": row["source_text"] = "câu khác"
    if fault == "evidence": row["evidence"] = "vỏ đạn"
    if fault == "foreign_id": row["existing_code_id"] = "foreign"
    if fault == "missing_code": row["comparisons"].pop()
    if fault == "duplicate": row["comparisons"].append(deepcopy(row["comparisons"][0]))
    if fault == "fake_exclusion": row["comparisons"][0]["excluded_by"] = "Không nhận vật kê"
    if fault == "false_goal": row["comparisons"][1]["goal_match"] = False
    if fault == "wrong_relation": row["comparisons"][1]["relation"] = "DIFFERENT"
    if fault == "merge": row["absorbed_code_ids"] = ["block"]
    result, meta, calls = execute(monkeypatch, {"decisions": [row]})
    assert result.decisions[0].decision == "UNCERTAIN"
    assert result.decisions[0].policy_gates["contract_error"]
    assert len(calls) == 2  # Một lần sửa contract cho đúng ý; không phân xử ngữ nghĩa lần thứ ba.
    assert meta["runs"][0]["contract_errors"][0]


def test_one_broken_row_does_not_discard_good_row_and_retry_is_single(monkeypatch):
    ideas, source, candidates = fixture(2)
    broken = final(1, evidence="bịa")
    requests = []
    def reply(*args, **kwargs):
        requests.append(kwargs["prompt"])
        return {"decisions": [final(), broken]} if len(requests) == 1 else {"decisions": [final(1)]}, {}
    monkeypatch.setattr(judge, "chat_json", reply)
    result, meta = judge.adjudicate_decisions(ITEM, ideas, source, candidates, object())
    assert all(row.decision == "MATCH_EXISTING" for row in result.decisions)
    assert len(requests) == 2
    retry_payload, _ = json.JSONDecoder().raw_decode(requests[1][requests[1].index('{"codes":'):])
    assert [case["idea_index"] for case in retry_payload["cases"]] == [1]
    assert meta["runs"][0]["checks"][0]["idea_index"] == 0
    assert meta["runs"][0]["contract_errors"][1]


def test_auxiliary_uncertainty_does_not_veto_clear_match(monkeypatch):
    row = final()
    row["comparisons"][0].update(relation="UNCERTAIN", competes_for_assignment=False)
    result, _, calls = execute(monkeypatch, {"decisions": [row]})
    assert result.decisions[0].decision == "MATCH_EXISTING" and len(calls) == 1


def test_competing_uncertainty_is_semantic_not_technical(monkeypatch):
    row = final()
    row["comparisons"][0].update(relation="UNCERTAIN", competes_for_assignment=True)
    result, meta, calls = execute(monkeypatch, {"decisions": [row]})
    assert result.decisions[0].decision == "UNCERTAIN" and not result.decisions[0].policy_gates["technical_error"]
    assert meta["runs"][0]["checks"][0]["outcome"] == "SEMANTIC_AMBIGUITY" and len(calls) == 1


def test_two_matches_report_codebook_conflict(monkeypatch):
    row = final()
    row["comparisons"][0].update(relation="SAME_CATEGORY", goal_match=True, role_match=True)
    result, meta, _ = execute(monkeypatch, {"decisions": [row]})
    assert result.decisions[0].policy_gates["codebook_conflict"]
    assert "block" in result.decisions[0].reason and "support" in result.decisions[0].reason
    assert meta["runs"][0]["checks"][0]["outcome"] == "CODEBOOK_CONFLICT"


def test_grounding_failure_does_not_retry_semantic_verdict(monkeypatch):
    result, _, calls = execute(monkeypatch, {"decisions": [final(grounded=False, reason="Cơ chế chưa có căn cứ")]})
    assert result.decisions[0].decision == "UNCERTAIN" and len(calls) == 1


def test_provider_failure_does_not_fan_out_into_single_calls(monkeypatch):
    def fail(*args, **kwargs):
        raise judge.LLMJSONError("Provider không khả dụng")
    monkeypatch.setattr(judge, "chat_json", fail)
    ideas, source, candidates = fixture(2)
    result, meta = judge.adjudicate_decisions(ITEM, ideas, source, candidates, object())
    assert len(meta["runs"]) == 1
    assert all(row.policy_gates["technical_error"] for row in result.decisions)
    assert meta["runs"][0]["error"] and meta["runs"][0]["offered_code_ids"]


def test_curator_to_final_has_only_two_calls(monkeypatch):
    ideas, _, candidates = fixture()
    monkeypatch.setattr("app.pipeline.dynamic_mapping.rank_code_candidates", lambda *a, **kw: candidates)
    first = {"decisions": [{"idea_index": 0, "decision": "UNCERTAIN", "confidence": .5}]}
    client = FakeClient([json.dumps(first), json.dumps({"decisions": [final()]}, ensure_ascii=False)])
    result, meta = run_code_mapping(ITEM, ideas, candidates[0], client)
    assert client.chat.completions.calls == 2
    assert result.decisions[0].pair_verified
    assert meta["decision_verifier"]["reason"] == "handled_by_final_adjudication"


def test_diverse_candidates_preserve_function_neighbor_and_low_rank_chosen():
    rows = [{"id": str(i), "retrieval_score": 1 - i / 100,
             "signature_similarity": {"goal": .99 if i == 15 else .1},
             "definition_similarity": .99 if i == 14 else .1} for i in range(20)]
    selected = select_diverse_candidates(rows, 6, required_ids=["19"])
    ids = {row["id"] for row in selected}
    assert {"0", "14", "15", "19"} <= ids
    assert len(selected) == 6
    assert selected == sorted(selected, key=lambda row: -row["retrieval_score"])


def scope_fields():
    return {"code_name": "Vỏ đạn làm vật kê đỡ", "code_description": "Vỏ đạn chịu lực kê/chèn vật khác",
            "functional_signature": SIG, "inclusion_rules": ["Vỏ đạn kê đỡ vật bằng hình dạng chịu lực"],
            "exclusion_rules": ["Không gồm ném vỏ đạn để gây tác động"],
            "scope_variants": ["kê chân ghế khỏi nghiêng", "chèn dưới chân tủ"]}


def test_final_can_create_instead_of_keeping_wrong_curator_match(monkeypatch):
    row = final(decision="CREATE_NEW", code_relation="DIFFERENT", existing_code_id=None, **scope_fields())
    for comparison in row["comparisons"]:
        comparison.update(relation="DIFFERENT", goal_match=False, role_match=False)
    result, _, calls = execute(monkeypatch, {"decisions": [row]})
    decision = result.decisions[0]
    assert decision.decision == "CREATE_NEW" and decision.reviewed_by_challenger
    assert decision.positive_examples == ["chân chèn bàn ghế"] and len(calls) == 1


def test_final_can_propose_expansion_without_second_scope_proposal_call(monkeypatch):
    row = final(decision="EXPAND_EXISTING", code_relation="IDEA_BROADER_THAN_CODE", **scope_fields())
    row["comparisons"][1]["relation"] = "IDEA_BROADER_THAN_CODE"
    result, _, calls = execute(monkeypatch, {"decisions": [row]})
    decision = result.decisions[0]
    assert decision.decision == "EXPAND_EXISTING" and decision.reviewed_by_challenger
    assert decision.existing_code_id == "support" and len(calls) == 1
    assert not decision.pair_verified  # Việc sửa mã còn phải audit member thật ở worker.


def test_curator_cannot_self_declare_backend_verification(monkeypatch):
    from app.pipeline.dynamic_mapping import _normalize_curator_contract
    ideas, _, candidates = fixture()
    source = CuratorResult(decisions=[CuratorDecision(idea_index=0, decision="MATCH_EXISTING",
        existing_code_id="support", code_relation="IDEA_NARROWER_THAN_CODE", confidence=.99,
        reviewed_by_challenger=True, pair_verified=True,
        policy_gates={"final_adjudication_checked": True, "semantic_grounding_checked": True})])
    normalized = _normalize_curator_contract(source, ideas, candidates)
    assert not normalized.decisions[0].pair_verified and not normalized.decisions[0].reviewed_by_challenger
    monkeypatch.setattr(judge, "chat_json", lambda *a, **kw: ({"decisions": [final()]}, {}))
    result, meta = judge.adjudicate_decisions(ITEM, ideas, normalized, candidates, object())
    assert meta["runs"] and result.decisions[0].pair_verified


def test_output_budget_splits_large_comparison_batches(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "llm_provider", "byteplus")
    monkeypatch.setattr(settings, "llm_challenger_max_tokens", 4096)
    ideas, source, candidates = fixture(3)
    for rows in candidates.values():
        rows.extend({"id": f"other-{index}", "name": "Mã khác", "retrieval_score": .1} for index in range(10))
    seen = []
    def reply(*a, **kw):
        data, _ = json.JSONDecoder().raw_decode(kw["prompt"][kw["prompt"].index('{"codes":'):])
        indices = [case["idea_index"] for case in data["cases"]]
        seen.append(indices)
        rows = []
        for index in indices:
            row = final(index)
            row["comparisons"].extend({"code_id": f"other-{j}", "relation": "DIFFERENT", "reason": "Khác công dụng"}
                                      for j in range(10))
            rows.append(row)
        assert kw["max_tokens"] <= 4096
        return {"decisions": rows}, {}
    monkeypatch.setattr(judge, "chat_json", reply)
    result, _ = judge.adjudicate_decisions(ITEM, ideas, source, candidates, object())
    assert seen == [[0, 1, 2]]
    assert all(row.pair_verified for row in result.decisions)


def test_compact_coverage_and_single_target_relation(monkeypatch):
    row = final(code_relation="SAME_CATEGORY")  # Nhãn legacy khác nhưng cùng cho phép MATCH.
    row.pop("source_text")
    row["comparisons"] = row["comparisons"][1:]
    row["different_code_ids"] = ["block"]
    result, _, calls = execute(monkeypatch, {"decisions": [row]})
    assert len(calls) == 1
    assert result.decisions[0].code_relation == "IDEA_NARROWER_THAN_CODE"
    assert result.decisions[0].pair_verified


def test_compact_coverage_cannot_hide_competitor_or_duplicate_target(monkeypatch):
    row = final()
    row["different_code_ids"] = ["support"]
    result, _, _ = execute(monkeypatch, {"decisions": [row]})
    assert result.decisions[0].policy_gates["contract_error"]


def test_direct_acceptance_requires_backend_evidence_and_switch(monkeypatch):
    from app.config import settings
    from app.pipeline.dynamic_mapping import _normalize_curator_contract
    ideas, _, candidates = fixture()
    curator = CuratorResult(decisions=[CuratorDecision.model_validate(final())])
    checked = _normalize_curator_contract(curator, ideas, candidates)
    assert checked.decisions[0].policy_gates["curator_evidence_checked"]
    assert checked.decisions[0].existing_code_evaluations[0]["source"] == "CURATOR"
    monkeypatch.setattr(settings, "curator_direct_acceptance_enabled", True)
    monkeypatch.setattr(judge, "chat_json", lambda *a, **kw: pytest.fail("Không gọi lại quyết định đủ căn cứ"))
    result, meta = judge.adjudicate_decisions(ITEM, ideas, checked, candidates, object())
    assert result.decisions[0].pair_verified and meta["direct_indices"] == [0]
    assert _stored_match_review_reason(ideas.ideas[0], result.decisions[0]) is None


def test_single_request_over_budget_is_not_sent(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "llm_provider", "byteplus")
    monkeypatch.setattr(settings, "llm_challenger_max_tokens", 512)
    monkeypatch.setattr(judge, "chat_json", lambda *a, **kw: pytest.fail("Ngân sách không đủ"))
    ideas, source, candidates = fixture()
    result, meta = judge.adjudicate_decisions(ITEM, ideas, source, candidates, object())
    assert result.decisions[0].policy_gates["technical_error"]
    assert meta["runs"][0]["error_type"] == "RequestBudgetExceeded"
