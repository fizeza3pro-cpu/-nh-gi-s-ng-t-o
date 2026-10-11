"""Nhận xét phải có câu nguồn, không sửa điểm hay làm mất kết quả khi provider lỗi."""
import json
import pytest
from app.pipeline.creative_feedback import generate_creative_feedback
from app.pipeline.llm import LLMJSONError
from app.schemas.schemas import Item, PerIdeaScore
from tests.fake_llm import FakeClient


ITEM = Item(id="test", name="Vỏ đạn", description="Vỏ rỗng")
IDEA = PerIdeaScore(idea_id="idea-1", original="Làm lọ hoa", normalized="Lọ hoa", code="Chứa đựng",
                    originality=2, elaboration=1)
VALID = {"observations": [{"text": "Bạn khai thác đồ vật theo hướng tạo một vật dụng quen thuộc.",
                           "evidence": [{"idea_id": "idea-1", "quote": "Làm lọ hoa"}]}],
         "suggestion": "Nêu thêm cách giữ lọ đứng vững khi sử dụng."}


def test_feedback_is_grounded_and_does_not_request_rarity():
    client = FakeClient([json.dumps(VALID)])
    before = IDEA.model_dump()
    text, meta = generate_creative_feedback(ITEM, [IDEA], client, fallback="dự phòng")
    assert meta["status"] == "GENERATED"
    assert "Làm lọ hoa" in text and "Bạn có thể thử" in text
    assert IDEA.model_dump() == before
    prompt = client.chat.completions.requests[0]["messages"][0]["content"]
    assert '"originality":' not in prompt
    assert meta["depends_on_frequency"] is False


def test_fabricated_evidence_falls_back_without_extra_calls():
    bad = {**VALID, "observations": [{"text": "Nhận xét không có căn cứ trong bài làm.",
                                      "evidence": [{"idea_id": "idea-1", "quote": "Làm thức ăn"}]}]}
    client = FakeClient([json.dumps(bad)])
    text, meta = generate_creative_feedback(ITEM, [IDEA], client, fallback="dự phòng")
    assert text == "dự phòng" and meta["status"] == "FALLBACK"
    assert client.chat.completions.calls == 1


def test_quota_error_preserves_diagnostics_and_scores():
    client = FakeClient([RuntimeError("insufficient_quota")])
    text, meta = generate_creative_feedback(ITEM, [IDEA], client, fallback="đã có điểm")
    assert text == "đã có điểm" and meta["error_category"] == "QUOTA_EXHAUSTED"


def test_no_ideas_skips_feedback():
    client = FakeClient([])
    assert generate_creative_feedback(ITEM, [], client, fallback="không có ý")[1]["status"] == "SKIPPED"
    assert client.chat.completions.calls == 0


@pytest.mark.parametrize("prefix", ["", "Bạn có thể thử ", "Bạn có thể thử: Bạn có thể thử "])
def test_suggestion_label_is_rendered_once(prefix):
    data = {**VALID, "suggestion": prefix + VALID["suggestion"]}
    text, meta = generate_creative_feedback(ITEM, [IDEA], FakeClient([json.dumps(data)]), fallback="dự phòng")
    assert meta["status"] == "GENERATED"
    assert text.count("Bạn có thể thử") == 1
    assert meta["feedback"]["suggestion"] == VALID["suggestion"]
    assert not text.startswith("Trong bài làm này:")


def test_multiple_ideas_need_distinct_grounded_evidence():
    second = IDEA.model_copy(update={"idea_id": "idea-2", "original": "Làm chặn giấy"})
    data = json.loads(json.dumps(VALID))
    client = FakeClient([json.dumps(data)])
    _, meta = generate_creative_feedback(ITEM, [IDEA, second], client, fallback="dự phòng")
    assert meta["fallback_reason"] == "feedback_insufficient_evidence"
    data["observations"][0]["evidence"] *= 2
    _, meta = generate_creative_feedback(ITEM, [IDEA, second], FakeClient([json.dumps(data)]), fallback="dự phòng")
    assert meta["fallback_reason"] == "feedback_insufficient_evidence"
    data["observations"][0]["evidence"][1] = {"idea_id": "idea-2", "quote": "Làm chặn giấy"}
    text, meta = generate_creative_feedback(ITEM, [IDEA, second], FakeClient([json.dumps(data)]), fallback="dự phòng")
    assert meta["status"] == "GENERATED" and "Làm chặn giấy" in text


def test_prompt_edits_are_loaded_without_reimport(monkeypatch, tmp_path):
    from app.pipeline import creative_feedback
    prompt_path = tmp_path / "feedback.txt"
    monkeypatch.setattr(creative_feedback, "_TEMPLATE_PATH", prompt_path)
    client = FakeClient([json.dumps(VALID)])
    for marker in ("Nội dung thứ nhất", "Nội dung đã sửa"):
        prompt_path.write_text(marker + " {item_name} {ideas_json}", encoding="utf-8")
        generate_creative_feedback(ITEM, [IDEA], client, fallback="dự phòng")
        assert marker in client.chat.completions.requests[-1]["messages"][0]["content"]


@pytest.mark.parametrize("change", ["multiple_observations", "long_text"])
def test_verbose_feedback_falls_back_without_retry(change):
    bad = json.loads(json.dumps(VALID))
    if change == "multiple_observations":
        bad["observations"] *= 2
    else:
        bad["observations"][0]["text"] = "ý " * 81
    client = FakeClient([json.dumps(bad)])
    text, meta = generate_creative_feedback(ITEM, [IDEA], client, fallback="dự phòng")
    assert text == "dự phòng" and meta["status"] == "FALLBACK"
    assert client.chat.completions.calls == 1


def test_feedback_request_is_compact_and_output_budget_bounded(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_aux_max_tokens", 4096)
    assert settings.max_tokens_for("creative_feedback") <= 1024
    monkeypatch.setattr(settings, "llm_aux_max_tokens", 512)
    assert settings.max_tokens_for("creative_feedback") <= 512
    client = FakeClient([json.dumps(VALID)])
    generate_creative_feedback(ITEM, [IDEA], client, fallback="dự phòng")
    prompt = client.chat.completions.requests[0]["messages"][0]["content"]
    assert '"detail_evidence"' not in prompt
    assert '"original":"Làm lọ hoa"' in prompt
