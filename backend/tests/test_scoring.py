import json

from app.pipeline.scoring import run_scoring
from app.schemas.schemas import Item, PerIdeaScore
from tests.fake_llm import FakeClient


ITEM = Item(id="dua", name="Đũa", description="đôi đũa")
ORIGINALITY = [
    PerIdeaScore(normalized="x", code="C1", originality=2, elaboration=1),
    PerIdeaScore(normalized="y", code="C2", originality=1, elaboration=1),
]


def _run(elab_a: int, elab_b: int) -> str:
    return json.dumps(
        {
            "elaboration_scores": [
                {"normalized": "x", "code": "C1", "elaboration": elab_a},
                {"normalized": "y", "code": "C2", "elaboration": elab_b},
            ],
            "summary_vi": "ok",
        }
    )


def test_multi_run_averages_elaboration_per_idea():
    client = FakeClient([_run(3, 1), _run(4, 2), _run(5, 3)])
    result, meta = run_scoring(
        ITEM, 2, 2, ["C1", "C2"], ORIGINALITY, client, runs=3
    )

    assert meta["runs"] == 3
    assert result.per_idea_scores[0].originality == 2
    assert result.per_idea_scores[0].elaboration == 4
    assert result.per_idea_scores[1].originality == 1
    assert result.per_idea_scores[1].elaboration == 2
    assert result.originality == 3
    assert result.elaboration == 6


def test_no_valid_ideas_skips_llm():
    client = FakeClient(['{"should":"not be used"}'])
    result, meta = run_scoring(ITEM, 0, 0, [], [], client, runs=3)
    assert meta.get("skipped") is True
    assert result.fluency == 0
    assert client.chat.completions.calls == 0
