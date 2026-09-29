import json

from app.pipeline.scoring import count_meaningful_words, run_scoring
from app.schemas.schemas import Item, PerIdeaScore
from tests.fake_llm import FakeClient


ITEM = Item(id="dua", name="Đũa", description="đôi đũa")
ORIGINALITY = [
    PerIdeaScore(
        original="Buộc đũa thành giá đỡ điện thoại trên bàn để quay video",
        normalized="Giá đỡ điện thoại",
        code="GIÁ ĐỠ",
        originality=2,
        elaboration=1,
    ),
    PerIdeaScore(
        original="Làm que chỉ trên bảng",
        normalized="Que chỉ bảng",
        code="CHỈ DẪN",
        originality=1,
        elaboration=1,
    ),
]


def _facet(present: bool, evidence: str = "") -> dict:
    return {"present": present, "evidence": evidence}


def _run(*, hallucinate_target: bool = False, include_context: bool = True) -> str:
    target_evidence = "máy tính" if hallucinate_target else "điện thoại"
    return json.dumps(
        {
            "elaboration_analysis": [
                {
                    "original": ORIGINALITY[0].original,
                    "normalized": ORIGINALITY[0].normalized,
                    "code": "GIÁ ĐỠ",
                    "facets": {
                        "target": _facet(True, target_evidence),
                        "mechanism": _facet(True, "Buộc đũa"),
                        "context": _facet(include_context, "trên bàn" if include_context else ""),
                        "goal": _facet(True, "quay video"),
                    },
                },
                {
                    "original": ORIGINALITY[1].original,
                    "normalized": ORIGINALITY[1].normalized,
                    "code": "CHỈ DẪN",
                    "facets": {
                        "target": _facet(False),
                        "mechanism": _facet(False),
                        "context": _facet(True, "trên bảng"),
                        "goal": _facet(False),
                    },
                },
            ]
        },
        ensure_ascii=False,
    )


def test_multi_run_uses_grounded_majority_and_formula():
    client = FakeClient(
        [_run(), _run(), _run(hallucinate_target=True, include_context=False)]
    )
    result, meta = run_scoring(
        ITEM, 2, 2, ["GIÁ ĐỠ", "CHỈ DẪN"], ORIGINALITY, client, runs=3
    )

    assert meta["runs"] == 3
    assert result.per_idea_scores[0].originality == 2
    assert result.per_idea_scores[0].elaboration == 5
    assert set(result.per_idea_scores[0].elaboration_details) == {
        "target", "mechanism", "context", "goal"
    }
    assert result.per_idea_scores[1].originality == 1
    assert result.per_idea_scores[1].elaboration == 2
    assert result.originality == 3
    assert result.elaboration == 7
    assert "3.50/5" in result.summary_vi


def test_ungrounded_evidence_does_not_receive_a_point():
    client = FakeClient([_run(hallucinate_target=True)])
    result, _ = run_scoring(
        ITEM, 2, 2, ["GIÁ ĐỠ", "CHỈ DẪN"], ORIGINALITY, client, runs=1
    )

    assert "target" not in result.per_idea_scores[0].elaboration_details
    assert result.per_idea_scores[0].elaboration == 4


def test_meaningful_word_count_excludes_stopwords_and_item_name():
    assert count_meaningful_words("Dùng đũa để làm giá đỡ điện thoại", "Đũa") == 4


def test_prompt_contains_original_response():
    client = FakeClient([_run()])
    run_scoring(ITEM, 2, 2, ["GIÁ ĐỠ", "CHỈ DẪN"], ORIGINALITY, client, runs=1)

    prompt = client.chat.completions.requests[0]["messages"][0]["content"]
    assert ORIGINALITY[0].original in prompt


def test_no_valid_ideas_skips_llm():
    client = FakeClient(['{"should":"not be used"}'])
    result, meta = run_scoring(ITEM, 0, 0, [], [], client, runs=3)
    assert meta.get("skipped") is True
    assert result.fluency == 0
    assert client.chat.completions.calls == 0


def test_creative_feedback_is_separate_from_numeric_scoring():
    feedback = {"observations": [{"text": "Bạn khai thác đồ vật theo hướng hỗ trợ hoạt động thực tế.",
                                  "evidence": [{"idea_id": "idea-0", "quote": "giá đỡ điện thoại"}]}],
                "suggestion": "Thử đổi đối tượng sử dụng để phát triển thêm một hướng công dụng."}
    client = FakeClient([_run(), json.dumps(feedback)])
    result, meta = run_scoring(ITEM, 2, 2, ["GIÁ ĐỠ", "CHỈ DẪN"], ORIGINALITY, client, runs=1)
    assert result.originality == 3 and result.elaboration == 7
    assert result.fluency == 2 and result.flexibility == 2
    assert "giá đỡ điện thoại" in result.summary_vi
    assert "Bạn có thể thử" in result.summary_vi
    assert meta["creative_feedback"]["status"] == "GENERATED"
    assert client.chat.completions.calls == 2
