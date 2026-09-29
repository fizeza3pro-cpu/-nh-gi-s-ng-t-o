"""Nhận xét phải có câu nguồn, không sửa điểm hay làm mất kết quả khi provider lỗi."""
import json
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
