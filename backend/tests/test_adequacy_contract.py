"""Hồi quy lỗi verifier làm cả response thất bại dù JSON đọc được."""
import json
import pytest
from app.pipeline.dynamic_mapping import run_idea_extraction
from app.pipeline.llm import LLMJSONError
from app.schemas.schemas import Item
from tests.fake_llm import FakeClient


SOURCE = {"line_index": 0, "original": "một câu chưa rõ nghĩa", "normalized": "một câu chưa rõ nghĩa",
          "status": "INVALID", "reason": "Chưa mô tả công dụng"}
ITEM = Item(id="test", name="Vật thử", description="Vật dùng cho kiểm thử")


@pytest.mark.parametrize("bad", [
    {"ideas": [{key: value for key, value in SOURCE.items() if key != "normalized"}]},
    {"ideas": []},
    {"ideas": [SOURCE, SOURCE]},
    {"ideas": [{**SOURCE, "line_index": 1}]},
    {"ideas": [{**SOURCE, "original": "câu khác"}]},
])
def test_adequacy_repairs_schema_and_source_contract(bad):
    client = FakeClient([json.dumps({"ideas": [SOURCE]}), json.dumps(bad), json.dumps({"ideas": [SOURCE]})])
    result, meta = run_idea_extraction(ITEM, [SOURCE["original"]], client)
    assert client.chat.completions.calls == 3
    assert result.ideas[0].status == "INVALID"
    assert result.ideas[0].idea_id
    assert meta["invalid_verifier"]["schema_repair_attempts"][1]["stage"] == "invalid_verifier_schema_repair"


def test_failed_verifier_keeps_diagnostics_and_reusable_extraction():
    client = FakeClient([json.dumps({"ideas": [SOURCE]}), '{"ideas": []}'])
    with pytest.raises(LLMJSONError) as caught:
        run_idea_extraction(ITEM, [SOURCE["original"]], client)
    error = caught.value
    assert error.metadata["error_type"] == "SchemaContractError"
    assert error.metadata["validation_errors"]
    assert error.metadata["response_id"] == "fake-3"
    assert error.extraction_checkpoint["ideas"][0]["original"] == SOURCE["original"]
    resumed = FakeClient([json.dumps({"ideas": [SOURCE]})])
    result, meta = run_idea_extraction(ITEM, [SOURCE["original"]], resumed, checkpoint=error.extraction_checkpoint)
    assert resumed.chat.completions.calls == 1
    assert meta["invalid_verifier"]["stage"] == "invalid_verifier"
    assert result.ideas[0].status == "INVALID"


def test_provider_error_keeps_metadata_without_fake_invalid():
    failure = LLMJSONError("Provider lỗi", metadata={"stage": "invalid_verifier", "retryable": False, "error_type": "AuthenticationError"})
    client = FakeClient([json.dumps({"ideas": [SOURCE]}), failure])
    with pytest.raises(LLMJSONError) as caught:
        run_idea_extraction(ITEM, [SOURCE["original"]], client)
    assert caught.value.extraction_checkpoint["ideas"]
    assert caught.value.metadata
