"""Hồi quy sự cố 05/11/2026: căn cứ chép câu chuẩn hoá, idea_index dạng chuỗi,
lỗi contract bị coi là lỗi kỹ thuật, output UUID phình và Curator bị cắt output."""
from copy import deepcopy

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.controllers import response_worker
from app.db import Base
from app.models.models import Item, ItemCode, Participant, Response
from app.pipeline import adjudication as judge
from app.pipeline import dynamic_mapping
from app.pipeline.adjudication import grounded_evidence
from app.pipeline.dynamic_mapping import _normalize_curator_contract, _shared_candidate_payload, run_code_mapping
from app.pipeline.llm import LLMJSONError
from app.schemas.schemas import CuratorDecision, CuratorResult, ExtractedIdea, IdeaExtractionResult, PerIdeaScore
from tests.test_decision_verifier import ITEM, SIG, final, fixture


def test_grounded_evidence_uses_source_not_paraphrase():
    assert grounded_evidence("dùng làm vật trang trí", "trang trí") == "trang trí"
    assert grounded_evidence("", "trồng cây") == "trồng cây"
    assert grounded_evidence("Chèn Bàn, ghế", "chân chèn bàn ghế") == "Chèn Bàn, ghế"
    assert grounded_evidence("vỏ đạn", "chân chèn bàn ghế") is None
    long_source = "tháo xẻng ra lấy tay cầm làm cần gạt để nạy tảng đá lớn bên đường"
    assert grounded_evidence("", long_source) is None


def test_curator_quoting_normalized_text_is_still_checked():
    """Ca thật: câu 'trang trí' nhưng Curator trích 'dùng làm vật trang trí'."""
    ideas = IdeaExtractionResult(ideas=[ExtractedIdea(original="kê bàn", normalized="dùng làm vật kê bàn",
                                                      status="VALID", functional_signature=SIG)])
    _, _, candidates = fixture()
    row = final(evidence="dùng làm vật kê bàn")
    row.pop("source_text")
    curator = CuratorResult(decisions=[CuratorDecision.model_validate(row)])
    checked = _normalize_curator_contract(curator, ideas, candidates)
    assert checked.decisions[0].decision == "MATCH_EXISTING"
    assert checked.decisions[0].policy_gates["curator_evidence_checked"]


def test_curator_payload_does_not_offer_normalized_text(monkeypatch):
    ideas, _, candidates = fixture()
    monkeypatch.setattr(dynamic_mapping, "rank_code_candidates", lambda *a, **kw: candidates)
    prompts = []

    def reply(*args, **kwargs):
        prompts.append(kwargs["prompt"])
        return {"decisions": [final()]}, {}
    monkeypatch.setattr(dynamic_mapping, "chat_json", reply)
    monkeypatch.setattr(judge, "chat_json", reply)
    run_code_mapping(ITEM, ideas, candidates[0], object())
    assert '"normalized"' not in prompts[0]


def test_string_idea_index_is_accepted(monkeypatch):
    row = final()
    row["idea_index"] = "0"
    calls = []

    def reply(*args, **kwargs):
        calls.append(kwargs)
        return {"decisions": [deepcopy(row)]}, {}
    monkeypatch.setattr(judge, "chat_json", reply)
    ideas, source, candidates = fixture()
    result, _ = judge.adjudicate_decisions(ITEM, ideas, source, candidates, object())
    assert result.decisions[0].decision == "MATCH_EXISTING" and len(calls) == 1


def test_challenger_uses_short_aliases_and_restores_ids(monkeypatch):
    prompts = []

    def reply(*args, **kwargs):
        prompts.append(kwargs["prompt"])
        row = final()
        row["existing_code_id"] = "C02"
        for comparison, alias in zip(row["comparisons"], ("C01", "C02")):
            comparison["code_id"] = alias
        return {"decisions": [row]}, {}
    monkeypatch.setattr(judge, "chat_json", reply)
    ideas, source, candidates = fixture()
    result, _ = judge.adjudicate_decisions(ITEM, ideas, source, candidates, object())
    assert '"id":"C01"' in prompts[0] and '"support"' not in prompts[0]
    assert result.decisions[0].existing_code_id == "support" and result.decisions[0].pair_verified


def test_alias_payload_only_rewrites_id_fields():
    aliases = {}
    text = _shared_candidate_payload([{"idea_index": 0, "original": "support",
                                       "nearest_codes": [{"id": "support", "name": "support"}]}],
                                     alias_map=aliases)
    assert aliases == {"C01": "support"}
    assert '"original":"support"' in text and '"name":"support"' in text and '"id":"C01"' in text


def test_contract_error_gets_one_delayed_retry_then_waits_for_admin(monkeypatch):
    """Sự cố 07/11/2026: ý sai contract từng treo PENDING_REVIEW 11 ngày vì không có lịch chạy lại."""
    from datetime import datetime, timedelta, timezone
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = lambda: Session(engine)
    monkeypatch.setattr(response_worker, "SessionLocal", factory)
    monkeypatch.setattr(response_worker.settings, "mock_mode", False)
    monkeypatch.setattr(response_worker, "chat_client", lambda: object())
    monkeypatch.setattr(response_worker, "make_embedding_client", lambda: None)
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(original="kê bàn", normalized="kê bàn",
        status="VALID", object_used="Balo", functional_signature=SIG)])
    monkeypatch.setattr(response_worker, "run_idea_extraction", lambda *a, **kw: (extraction, {}))
    broken = judge._unresolved(CuratorDecision(idea_index=0, decision="UNCERTAIN", confidence=0),
                               "Kết quả phân xử sai contract", "CONTRACT_ERROR")
    monkeypatch.setattr(response_worker, "run_code_mapping", lambda *a, **kw: (CuratorResult(decisions=[broken]), {}))
    with factory() as db:
        db.add_all([Item(id="bag", name="Balo"), Participant(id="p")])
        db.add(ItemCode(id="c", item_id="bag", name="Balo kê", normalized_name="ke", functional_signature=SIG))
        db.add(Response(id="r", item_id="bag", participant_id="p", raw_input="kê bàn", input_lines=["kê bàn"],
                        mapping={}, scoring={}, processing_state="RUNNING", processing_claim_token="t"))
        db.commit()
    before = datetime.now(timezone.utc)
    response_worker._run_mapping("r", "t")
    with factory() as db:
        row = db.get(Response, "r")
        idea = row.ideas[0]
        # Lần đầu: hẹn một lượt chạy lại sau CONTRACT_RETRY_DELAY_SECONDS, không phải lỗi kỹ thuật.
        assert idea.review_payload["issue_type"] == "CONTRACT_ERROR" and idea.coding_state == "RESOLVING"
        next_at = row.resolution_next_at.replace(tzinfo=row.resolution_next_at.tzinfo or timezone.utc)
        assert next_at >= before + timedelta(seconds=response_worker.settings.contract_retry_delay_seconds - 5)
        assert row.mapping_checkpoint["technical_retry_indices"] == [0]
        assert row.mapping_checkpoint["contract_retry_count"] == 1 and row.resolution_attempts == 0
        row.processing_claim_token = "t2"
        db.commit()
    # Lượt hẹn giờ vẫn sai contract: hết lượt, chờ admin, không lên lịch tiếp.
    response_worker._run_mapping("r", "t2", resolving=True)
    with factory() as db:
        row = db.get(Response, "r")
        assert row.resolution_next_at is None and row.mapping_checkpoint["technical_retry_indices"] == []
        assert row.ideas[0].coding_state == "UNRESOLVED" and row.resolution_attempts == 0


def test_truncated_curator_splits_in_half_instead_of_single_calls(monkeypatch):
    ideas, source, candidates = fixture(4)
    monkeypatch.setattr(dynamic_mapping, "rank_code_candidates", lambda *a, **kw: candidates)
    monkeypatch.setattr(dynamic_mapping, "run_code_challenger", lambda item, ideas, cand, curator, *a: (curator, {}))
    stages = []

    def reply(*args, **kwargs):
        stages.append(kwargs["stage"])
        if len(stages) == 1:
            raise LLMJSONError("cắt", metadata={"error_type": "LLMJSONError", "error_category": "OUTPUT_TRUNCATED"})
        prompt = kwargs["prompt"]
        indices = [index for index in range(4) if f'"idea_index":{index}' in prompt]
        return {"decisions": [final(index) for index in indices]}, {}
    monkeypatch.setattr(dynamic_mapping, "chat_json", reply)
    result, meta = run_code_mapping(ITEM, ideas, candidates[0], object())
    assert stages == ["code_curator"] * 3
    assert meta["split_reason"] == "output_truncated" and len(meta["batches"]) == 2
    assert sorted(decision.idea_index for decision in result.decisions) == [0, 1, 2, 3]


# --- Contract prompt gọn (nhóm A) và tiêu chí hợp lệ (nhóm B) ---

def test_scoring_contract_without_echoed_source():
    """Định danh bằng idea_id; không bắt model chép original/normalized/code."""
    import json as _json
    from app.pipeline.scoring import run_scoring
    from tests.fake_llm import FakeClient
    from tests.test_scoring import ITEM as DUA, ORIGINALITY
    ideas = [score.model_copy(update={"idea_id": f"idea-{index}"}) for index, score in enumerate(ORIGINALITY)]
    reply = {"elaboration_analysis": [
        {"idea_id": "idea-1", "facets": {"target": {"evidence": "trên bảng"}}},
        {"idea_id": "idea-0", "facets": {"target": {"evidence": "điện thoại"}, "context": {"evidence": "trên bàn"},
                                         "goal": {"evidence": "bịa đặt"}}},
    ]}
    client = FakeClient([_json.dumps(reply, ensure_ascii=False), "{}"])
    result, _ = run_scoring(DUA, 2, 2, ["GIÁ ĐỠ", "CHỈ DẪN"], ideas, client, runs=1)
    assert [score.elaboration for score in result.per_idea_scores] == [3, 2]  # bằng chứng bịa bị loại
    rules = client.chat.completions.requests[0]["messages"][0]["content"].split("Đồ vật:")[0]
    assert '"original"' not in rules and '"present"' not in rules


def test_scope_audit_matches_checks_by_index_without_copying_sources(monkeypatch):
    import json as _json
    from contextlib import contextmanager
    from app.pipeline import scope_audit
    from app.schemas.schemas import Item as ItemSchema
    from tests.fake_llm import FakeClient

    @contextmanager
    def factory():
        yield None
    monkeypatch.setattr(scope_audit, "member_rows", lambda db, ids: [("old", "đựng sách")])
    check = lambda index: {"index": index, "relation": "SAME_CATEGORY", "goal_match": True, "role_match": True,
                           "exclusion_hit": False, "evidence": "", "reason": "Cùng chức năng"}
    # Trả ngược thứ tự: backend phải ghép theo index, không theo vị trí.
    client = FakeClient([_json.dumps({"checks": [check(1), check(0)]})])
    decision = CuratorDecision(idea_index=0, decision="EXPAND_EXISTING", existing_code_id="a",
                               functional_signature=SIG, confidence=.9)
    result, audits, guards = scope_audit.verify_expansions(
        factory, ItemSchema(id="bag", name="Balo", description="Khoang chứa"),
        IdeaExtractionResult(ideas=[ExtractedIdea(original="đựng đồ", normalized="đựng đồ", status="VALID")]),
        CuratorResult(decisions=[decision]), [], client)
    assert result.decisions[0].decision == "EXPAND_EXISTING" and guards
    assert '"index": 0' in client.chat.completions.requests[0]["messages"][0]["content"]


def test_pair_verifier_accepts_missing_source_text_and_short_empty_evidence():
    import json as _json
    from app.pipeline.semantic_verifier import verify_pair
    from app.schemas.schemas import Item as ItemSchema
    from tests.fake_llm import FakeClient
    reply = {"relation": "SAME_CATEGORY", "goal_match": True, "role_match": True,
             "exclusion_hit": False, "evidence": "", "reason": "Cùng chức năng chứa đồ."}
    verdict, _ = verify_pair(ItemSchema(id="bag", name="Balo", description=""), "đựng sách",
                             {"name": "Chứa đồ"}, FakeClient([_json.dumps(reply, ensure_ascii=False)]))
    assert verdict.source_text == "đựng sách" and verdict.evidence == "đựng sách"


def test_prompts_have_static_rules_first_and_no_item_specific_examples():
    from pathlib import Path
    prompts = Path(__file__).resolve().parents[1] / "app/pipeline/prompts"
    for name in ("code_curator", "code_challenger", "idea_extraction", "scoring", "pair_verifier",
                 "scope_member_audit", "creative_feedback", "code_batch_reconciler"):
        text = (prompts / f"{name}.txt").read_text(encoding="utf-8")
        first_data = min(text.find("{" + key + "}") for key in ("item_name", "item_description")
                         if "{" + key + "}" in text)
        assert first_data > len(text) * 0.85, name
        for leaked in ("thức ăn", "quân nhu", "chống nước", "nuôi sinh vật", "trang sức", "xúc vật liệu rời"):
            assert leaked not in text, (name, leaked)
    extraction = (prompts / "idea_extraction.txt").read_text(encoding="utf-8")
    for rule in ("bán", "cho mượn", "tặng", "tái chế", "nung chảy", "phế liệu"):
        assert rule in extraction
    # Gia công tạo hình (cắt, mài...) không bị gộp vào nhóm phá bỏ hình dạng lấy chất liệu.
    assert "Gia công tạo hình vẫn VALID" in extraction and "mài" in extraction


def test_scoring_prompt_excludes_core_use_and_is_deterministic_by_default():
    """Sự cố 06/11/2026: động từ/tân ngữ của công dụng bị tính là chi tiết; temperature 0.4 gây dao động."""
    from pathlib import Path
    from app.config import Settings
    text = (Path(__file__).resolve().parents[1] / "app/pipeline/prompts/scoring.txt").read_text(encoding="utf-8")
    assert "Công dụng cốt lõi" in text and "Động từ chính" in text
    assert Settings.model_fields["scoring_temperature"].default == 0.0
    assert Settings.model_fields["creative_feedback_temperature"].default == 0.2


def _elaboration_reply(evidence: str) -> str:
    import json as _json
    return _json.dumps({"elaboration_analysis": [{"idea_id": "a", "facets": {"context": {"evidence": evidence}}}]},
                       ensure_ascii=False)


def test_scoring_majority_tolerates_one_failed_run_and_counts_its_usage():
    import pytest as _pytest
    from app.pipeline.scoring import run_scoring
    from tests.fake_llm import FakeClient
    from tests.test_scoring import ITEM as DUA
    idea = PerIdeaScore(idea_id="a", original="kê chân bàn trong bếp", normalized="kê bàn", code="KÊ",
                        originality=0, elaboration=1)
    # Lượt 2 sai contract; lượt 1 và 3 đồng thuận "trong bếp" → vẫn đạt đa số 2/3.
    client = FakeClient([_elaboration_reply("trong bếp"), '{"elaboration_analysis": []}',
                         _elaboration_reply("trong bếp"), "{}"])
    result, meta = run_scoring(DUA, 1, 1, ["KÊ"], [idea], client, runs=3)
    assert result.per_idea_scores[0].elaboration == 2
    assert meta["successful_runs"] == 2 and len(meta["failed_runs"]) == 1 and meta["majority_threshold"] == 2
    # Hai lượt lỗi thì không đủ đa số, không được chấm từ một lượt duy nhất.
    client = FakeClient([_elaboration_reply("trong bếp"), "{}", "{}"])
    with _pytest.raises(LLMJSONError):
        run_scoring(DUA, 1, 1, ["KÊ"], [idea], client, runs=3)


def test_single_run_detail_is_not_kept_without_majority():
    from app.pipeline.scoring import run_scoring
    from tests.fake_llm import FakeClient
    from tests.test_scoring import ITEM as DUA
    idea = PerIdeaScore(idea_id="a", original="kê chân bàn trong bếp", normalized="kê bàn", code="KÊ",
                        originality=0, elaboration=1)
    client = FakeClient([_elaboration_reply("trong bếp"), _elaboration_reply(""), _elaboration_reply(""), "{}"])
    result, _ = run_scoring(DUA, 1, 1, ["KÊ"], [idea], client, runs=3)
    assert result.per_idea_scores[0].elaboration == 1


def test_flat_elaboration_contract_is_read():
    """JSON lồng 4 cấp từng bị model quên một dấu ngoặc; contract phẳng giảm lỗi này."""
    import json as _json
    from app.pipeline.scoring import run_scoring
    from tests.fake_llm import FakeClient
    from tests.test_scoring import ITEM as DUA
    idea = PerIdeaScore(idea_id="a", original="kê chân bàn trong bếp để khỏi cập kênh", normalized="kê bàn",
                        code="KÊ", originality=0, elaboration=1)
    flat = _json.dumps({"elaboration_analysis": [{"idea_id": "a", "target": "", "mechanism": "",
                        "context": "trong bếp", "goal": "để khỏi cập kênh"}]}, ensure_ascii=False)
    result, _ = run_scoring(DUA, 1, 1, ["KÊ"], [idea], FakeClient([flat, flat, flat, "{}"]), runs=3)
    assert result.per_idea_scores[0].elaboration == 3


# --- Sự cố 06/11/2026 (Ghim kẹp giấy): quan hệ BROADER dùng sai, retry rời rạc, EXPAND hai lần ---

def test_broader_with_both_flags_false_is_read_as_different(monkeypatch):
    """Ca thật "tăm xỉa răng" so với "chọc sim": BROADER kèm goal/role false là khác chức năng."""
    row = final(decision="CREATE_NEW", existing_code_id=None, code_name="Vỏ đạn làm cọc chèn",
                code_description="Dùng Vỏ đạn làm cọc chèn khe hở.",
                functional_signature={"goal": "chèn khe", "object_role": "cọc chèn", "mechanism": "nêm chặt"},
                inclusion_rules=["Vỏ đạn được nêm vào khe để chèn chặt hai mặt"],
                exclusion_rules=["Không gồm việc kê đỡ vật nặng từ bên dưới"],
                scope_variants=["nêm vỏ đạn vào khe cửa", "chèn vỏ đạn vào kẽ gỗ"])
    row.pop("source_text")
    row["comparisons"] = [
        {"code_id": "block", "relation": "IDEA_BROADER_THAN_CODE", "goal_match": False, "role_match": False,
         "reason": "Có liên quan nhưng khác chức năng."},
        {"code_id": "support", "relation": "DIFFERENT", "reason": "Khác chức năng."}]
    result, meta = judge.adjudicate_decisions(ITEM, *_one_call(monkeypatch, row))
    decision = result.decisions[0]
    assert decision.decision == "CREATE_NEW" and decision.policy_gates["broader_relabeled_different"]


def test_broader_with_matching_flags_still_blocks_create(monkeypatch):
    row = final(decision="CREATE_NEW", existing_code_id=None)
    row.pop("source_text")
    row["comparisons"][0].update(relation="IDEA_BROADER_THAN_CODE", goal_match=True, role_match=True)
    row["comparisons"][1].update(relation="DIFFERENT", goal_match=False, role_match=False)
    result, _ = judge.adjudicate_decisions(ITEM, *_one_call(monkeypatch, row))
    assert result.decisions[0].policy_gates["contract_error"]


def _one_call(monkeypatch, row):
    """Trả đúng một quyết định cho mọi lượt gọi; dùng chung cho các test Challenger ở trên."""
    ideas, source, candidates = fixture()
    monkeypatch.setattr(judge, "chat_json", lambda *a, **kw: ({"decisions": [deepcopy(row)]}, {}))
    return ideas, source, candidates, object()


def test_contract_retries_are_batched_into_one_request(monkeypatch):
    ideas, source, candidates = fixture(3)
    prompts = []

    def reply(*args, **kwargs):
        prompts.append(kwargs["prompt"])
        if len(prompts) == 1:
            return {"decisions": [final(0), final(1, evidence="bịa"), final(2, evidence="bịa")]}, {}
        return {"decisions": [final(1), final(2)]}, {}
    monkeypatch.setattr(judge, "chat_json", reply)
    result, meta = judge.adjudicate_decisions(ITEM, ideas, source, candidates, object())
    assert len(prompts) == 2  # một lượt chính + một lượt sửa chung cho hai ý lỗi
    assert all(decision.decision == "MATCH_EXISTING" for decision in result.decisions)
    assert '"idea_index":1' in prompts[1] and '"idea_index":2' in prompts[1] and '"idea_index":0' not in prompts[1]


def test_second_expand_on_same_code_in_one_persist_is_held_for_new_scope():
    """Ca thật "vòng tay" rồi "vòng chân": EXPAND thứ hai dựa trên phạm vi cũ không được ghi đè."""
    import uuid
    from sqlalchemy.orm import Session as OrmSession
    from app.pipeline.codebook_service import persist_mapping
    from app.schemas.schemas import FunctionalSignature
    from tests.test_dynamic_codebook import _engine, _response
    engine = _engine()
    Base.metadata.create_all(engine)
    with OrmSession(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại")
        response = _response(participant.id, item.id)
        code = ItemCode(item_id=item.id, name="Vỏ đạn làm vòng cổ", normalized_name="vo dan lam vong co",
                        description="Xâu Vỏ đạn thành vòng đeo cổ.",
                        functional_signature={"goal": "trang trí", "object_role": "hạt xâu", "mechanism": "xâu"},
                        inclusion_rules=["Vỏ đạn xâu thành vòng đeo ở cổ"], exclusion_rules=["Đồ trang trí không đeo"],
                        positive_examples=["xâu thành vòng cổ"], confidence=0.9)
        db.add_all([participant, item, response, code])
        db.flush()
        signature = FunctionalSignature(goal="trang trí cơ thể", object_role="hạt xâu trang sức", mechanism="xâu nối")
        extraction = IdeaExtractionResult(ideas=[
            ExtractedIdea(original=text, normalized=text, status="VALID", object_used="Vỏ đạn",
                          functional_signature=signature) for text in ("xâu thành vòng tay", "xâu thành vòng chân")])
        expand = lambda index, name, description: CuratorDecision(
            idea_index=index, decision="EXPAND_EXISTING", code_relation="IDEA_BROADER_THAN_CODE",
            existing_code_id=code.id, code_name=name, code_description=description, functional_signature=signature,
            inclusion_rules=["Vỏ đạn được xâu nối thành đồ trang sức đeo trên cơ thể"],
            exclusion_rules=["Không gồm đồ trang trí treo tường không đeo trên người"],
            scope_variants=["xâu vỏ đạn làm lắc tay", "xâu vỏ đạn làm dây chuyền"],
            positive_examples=[extraction.ideas[index].original], reviewed_by_challenger=True, confidence=0.9)
        curator = CuratorResult(decisions=[
            expand(0, "Vỏ đạn làm trang sức đeo trên người", "Xâu Vỏ đạn thành trang sức đeo trên người."),
            expand(1, "Vỏ đạn làm vòng cổ và vòng chân", "Xâu Vỏ đạn thành vòng cổ, vòng chân.")])
        mapping, uncertain = persist_mapping(db, item=item, response=response, extraction=extraction, curator=curator,
                                             code_snapshots=[{"id": code.id, "scope_revision": 0}])
        assert uncertain is True
        assert code.description == "Xâu Vỏ đạn thành trang sức đeo trên người."  # không bị lượt sau thu hẹp
        assert code.scope_revision == 1
        assert mapping.ideas[0].code == "Vỏ đạn làm trang sức đeo trên người" and mapping.ideas[1].code is None
        held = [idea for idea in response.ideas if idea.line_index == 1][0]
        assert held.review_payload["issue_type"] == "STALE_SCOPE" and held.curator_decision == "STALE_SCOPE_REVIEW"
