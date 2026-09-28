import json
from contextlib import contextmanager
import pytest
from app.pipeline import scope_audit
from app.schemas.schemas import CuratorDecision, CuratorResult, ExtractedIdea, IdeaExtractionResult, Item
from tests.fake_llm import FakeClient


@contextmanager
def database():
    yield None


@pytest.mark.parametrize("neighbor_fits", [False, True])
def test_expansion_keeps_members_and_excludes_neighbor(monkeypatch, neighbor_fits):
    """Không mở rộng phạm vi nếu nó nuốt cả mã lân cận khác chức năng."""
    monkeypatch.setattr(scope_audit, "member_rows", lambda db, ids: [("old-id", "đựng sách")])
    sources = ["đựng sách", "đựng quân nhu", "đốt lấy nhiệt"]
    checks = [{"source_text": source, "evidence": source, "goal_match": True,
               "role_match": True, "exclusion_hit": False,
               "relation": "SAME_CATEGORY" if index < 2 or neighbor_fits else "DIFFERENT",
               "reason": "kiểm chứng"} for index, source in enumerate(sources)]
    client = FakeClient([json.dumps({"checks": checks}, ensure_ascii=False)])
    decision = CuratorDecision(idea_index=0, decision="EXPAND_EXISTING", existing_code_id="container", confidence=0.9)
    result, audit, guard = scope_audit.verify_expansions(database,
        Item(id="balo", name="Balo", description="Balo có khoang chứa"),
        IdeaExtractionResult(ideas=[ExtractedIdea(original=sources[1], normalized=sources[1], status="VALID")]),
        CuratorResult(decisions=[decision]),
        [{"id": "fuel", "positive_examples": [sources[2]]}], client)
    assert result.decisions[0].decision == ("UNCERTAIN" if neighbor_fits else "EXPAND_EXISTING")
    assert bool(guard) != neighbor_fits
    assert audit
    if not neighbor_fits:
        monkeypatch.setattr(scope_audit, "member_rows", lambda db, ids: [("old-id", sources[0]), ("new-id", "ý đến đồng thời")])
        guarded = scope_audit.guard_members(None, result, guard)
        assert guarded.decisions[0].decision == "UNCERTAIN"
