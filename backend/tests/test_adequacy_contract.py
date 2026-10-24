"""Hợp đồng Extraction ba trường: giữ dòng, không xét lại INVALID hoặc tìm án lệ."""
import json
import pytest
from app.pipeline.dynamic_mapping import run_idea_extraction, EXTRACTION_CONTRACT_VERSION
from app.pipeline.llm import LLMJSONError
from app.schemas.schemas import Item, FunctionalSignature, MappedIdea
from tests.fake_llm import FakeClient

ITEM = Item(id="test", name="Vật thử", description="Vật dùng cho kiểm thử")


def row(index=0, status="VALID"):
    return {"line_index": index, "normalized": "chặn giấy", "status": status,
            "object_used": ITEM.name, "functional_signature": {
                "goal": "giữ giấy", "object_role": "vật chặn", "mechanism": "trọng lượng"},
            "functional_evidence": {"goal": "chặn giấy"}, "reason": "Thiếu chức năng" if status == "INVALID" else ""}


def test_invalid_is_final_after_single_extraction():
    client = FakeClient([json.dumps({"ideas": [row(status="INVALID")]})])
    result, meta = run_idea_extraction(ITEM, ["câu không có công dụng"], client)
    assert client.chat.completions.calls == 1
    assert result.ideas[0].status == "INVALID"
    assert not result.ideas[0].review_required
    assert "invalid_verifier" not in meta


def test_ten_repeated_lines_are_independent_and_originals_are_backend_owned():
    client = FakeClient([json.dumps({"ideas": [dict(row(i), original="câu do AI đổi") for i in range(10)]})])
    result, _ = run_idea_extraction(ITEM, ["chặn giấy"] * 10, client)
    assert [i.line_index for i in result.ideas] == list(range(10))
    assert len({i.idea_id for i in result.ideas}) == 10
    assert all(i.original == "chặn giấy" and i.status == "VALID" for i in result.ideas)
    assert client.chat.completions.calls == 1
    prompt = client.chat.completions.requests[0]["messages"][0]["content"]
    for field in ['"original"', 'uses_target_object', 'target_object_role', '"transformation"', '"target"', '"context"']:
        assert field not in prompt
    assert set(result.ideas[0].functional_signature.model_dump()) == {"goal", "object_role", "mechanism"}


@pytest.mark.parametrize("bad", [[], [row(1), row(1)], [dict(row(1), status="DUPLICATE")],
    [dict(row(1), normalized=None)], [dict(row(1), inferred_signature_fields=["target"])]])
def test_repairs_only_bad_index_without_redoing_valid_line(bad):
    client = FakeClient([json.dumps({"ideas": [row(0), *bad]}), json.dumps({"ideas": [row(1)]})])
    result, _ = run_idea_extraction(ITEM, ["chặn giấy", "chặn giấy lần nữa"], client)
    prompt = client.chat.completions.requests[1]["messages"][0]["content"]
    assert '"line_index":1' in prompt and '"line_index":0' not in prompt.split('Chỉ JSON')[0]
    assert [i.original for i in result.ideas] == ["chặn giấy", "chặn giấy lần nữa"]
    assert client.chat.completions.calls == 2


def test_failure_preserves_partial_extraction_for_technical_retry():
    client = FakeClient([json.dumps({"ideas": [row(0)]}), json.dumps({"ideas": []})])
    with pytest.raises(LLMJSONError) as caught:
        run_idea_extraction(ITEM, ["chặn giấy", "chặn giấy lần nữa"], client)
    checkpoint = caught.value.extraction_checkpoint
    assert checkpoint["contract_version"] == EXTRACTION_CONTRACT_VERSION
    assert [r["line_index"] for r in checkpoint["ideas"]] == [0]
    resumed = FakeClient([json.dumps({"ideas": [row(1)]})])
    result, _ = run_idea_extraction(ITEM, ["chặn giấy", "chặn giấy lần nữa"], resumed, checkpoint=checkpoint)
    assert resumed.chat.completions.calls == 1
    assert len(result.ideas) == 2


def test_fake_evidence_is_removed_and_inference_recorded():
    source = row()
    source["functional_evidence"] = {"goal": "bằng chứng bịa", "object_role": "chặn giấy"}
    result, _ = run_idea_extraction(ITEM, ["chặn giấy"], FakeClient([json.dumps({"ideas": [source]})]))
    assert result.ideas[0].functional_evidence["goal"] == ""
    assert "goal" in result.ideas[0].inferred_signature_fields


def test_history_can_still_read_duplicate_and_old_signature_without_mutation():
    raw = {"original": "ý cũ", "normalized": "ý cũ", "status": "DUPLICATE", "is_valid": False,
           "functional_signature": {"goal": "giữ giấy", "target": "giấy", "context": "cũ", "transformation": "cũ"}}
    before = json.dumps(raw, sort_keys=True)
    mapped = MappedIdea.model_validate(raw)
    assert mapped.status == "DUPLICATE"
    assert set(mapped.functional_signature.model_dump()) == {"goal", "object_role", "mechanism"}
    assert json.dumps(raw, sort_keys=True) == before
    assert "context" not in FunctionalSignature.model_fields
