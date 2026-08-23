import json

from app.schemas import Item, MappedIdea, MappingResult
from app.pipeline.scoring import run_scoring
from tests.fake_llm import FakeClient


ITEM = Item(id="dua", name="Đũa", description="đôi đũa", codes=["C1", "C2"])

MAPPING = MappingResult(
    ideas=[
        MappedIdea(original="a", normalized="x", code="C1", status="VALID"),
        MappedIdea(original="b", normalized="y", code="C2", status="VALID"),
        MappedIdea(original="c", normalized="z", code="C1", status="DUPLICATE"),
    ]
)


def _run(orig_a, elab_a, orig_b, elab_b):
    return json.dumps(
        {
            "fluency": 2,
            "flexibility": 2,
            "flexibility_codes": ["C1", "C2"],
            "originality": orig_a + orig_b,
            "elaboration": elab_a + elab_b,
            "per_idea_scores": [
                {"normalized": "x", "code": "C1", "originality": orig_a, "elaboration": elab_a},
                {"normalized": "y", "code": "C2", "originality": orig_b, "elaboration": elab_b},
            ],
            "summary_vi": "ok",
        }
    )


def test_multi_run_averages_per_idea():
    client = FakeClient([_run(2, 3, 0, 1), _run(1, 4, 1, 2), _run(0, 5, 2, 3)])
    result, meta = run_scoring(ITEM, MAPPING, client, runs=3)

    assert meta["runs"] == 3
    # A orig avg (2+1+0)/3 = 1.0 → 1 ; elab (3+4+5)/3 = 4 → 4
    assert result.per_idea_scores[0].originality == 1
    assert result.per_idea_scores[0].elaboration == 4
    # B orig avg (0+1+2)/3 = 1.0 → 1 ; elab (1+2+3)/3 = 2 → 2
    assert result.per_idea_scores[1].originality == 1
    assert result.per_idea_scores[1].elaboration == 2
    assert result.originality == 2
    assert result.elaboration == 6
    assert meta["per_idea_averages"][0]["originality"] == 1.0


def test_no_valid_ideas_skips_llm():
    empty_mapping = MappingResult(
        ideas=[MappedIdea(original="x", normalized="", code="", status="INVALID")]
    )
    client = FakeClient(['{"should":"not be used"}'])
    result, meta = run_scoring(ITEM, empty_mapping, client, runs=3)
    assert meta.get("skipped") is True
    assert result.fluency == 0
    assert client.chat.completions.calls == 0
