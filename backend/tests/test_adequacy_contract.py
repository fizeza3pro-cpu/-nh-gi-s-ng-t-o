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


@pytest.mark.parametrize("stage", ["invalid_verifier", "invalid_policy_repair"])
def test_inferred_fields_repair_explains_enum_and_preserves_source(stage):
    from app.pipeline.dynamic_mapping import _validate_adequacy_result
    from app.schemas.schemas import ExtractedIdea

    fields = ["goal", "object_role", "mechanism"]
    source = {**SOURCE, "line_index": 1}
    bad = {"ideas": [SOURCE, {**source, "inferred_signature_fields": fields + ["target", "context", "transformation"]}]}
    good = {"ideas": [SOURCE, {**source, "inferred_signature_fields": fields}]}
    client = FakeClient([json.dumps(good)])
    result, meta = _validate_adequacy_result(
        bad, {}, [ExtractedIdea(**SOURCE), ExtractedIdea(**source)], "Kiểm chứng", client, stage,
    )
    assert client.chat.completions.calls == 1
    assert [idea.original for idea in result.ideas] == [SOURCE["original"], source["original"]]
    assert result.ideas[1].inferred_signature_fields == fields
    assert result.ideas[1].status == "INVALID"
    prompt = client.chat.completions.requests[0]["messages"][0]["content"]
    assert '"expected": "\'goal\', \'object_role\' or \'mechanism\'"' in prompt
    assert 'không đưa "target", "context", "transformation"' in prompt
    assert meta["schema_repair_attempts"][-1]["stage"] == stage + "_schema_repair"


def test_repeated_invalid_enum_keeps_expected_values_without_input():
    from app.pipeline.dynamic_mapping import _validate_adequacy_result
    from app.schemas.schemas import ExtractedIdea

    bad = {"ideas": [{**SOURCE, "inferred_signature_fields": ["target", "context", "transformation"]}]}
    client = FakeClient([json.dumps(bad)])
    with pytest.raises(LLMJSONError) as caught:
        _validate_adequacy_result(bad, {}, [ExtractedIdea(**SOURCE)], "Kiểm chứng", client, "invalid_verifier")
    assert client.chat.completions.calls == 1
    errors = caught.value.metadata["validation_errors"]
    assert len(errors) == 3
    assert all(error["expected"] == "'goal', 'object_role' or 'mechanism'" for error in errors)
    assert all("input" not in error for error in errors)
