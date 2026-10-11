"""Kiểm tra nạp ba corpus độc lập, tính điểm thật và không trộn nguồn SURVEY."""
from collections import Counter

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base
from app.models.models import Item, ItemCode, Response, ResponseIdea, Participant
from app.pipeline.pilot_reference import REFERENCES, corpus_options, plan_reference
from app.pipeline.embedding import embed_texts
from app.pipeline.codebook_service import item_is_ready_for_scoring, qualifying_idea_count
from scripts.import_shell_reference import insert_reference
from scripts.seed_shell_distribution import build_corpus, populate


@pytest.mark.parametrize("item_id", REFERENCES)
def test_corpus_has_no_repeated_code_or_idea_within_response(item_id):
    options = corpus_options(item_id)
    corpus = build_corpus(options["counts"], options["variants"])
    assert len(corpus) == 15
    assert all(len(bucket) == len({key for key, _, _ in bucket}) == 10 for bucket in corpus)
    assert Counter(key for bucket in corpus for key, _, _ in bucket) == options["counts"]
    assert len({entry["name"] for entry in REFERENCES[item_id]}) == 20
    for spec in REFERENCES[item_id]:
        assert spec["inclusion_rules"] and spec["exclusion_rules"]
        assert all(spec["functional_signature"][field] for field in ("goal", "object_role", "mechanism"))


def test_three_corpora_atomic_idempotent_and_scores_follow_frequency(monkeypatch):
    monkeypatch.setattr(settings, "survey_data_source", "PILOT")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        items = [Item(id=item_id, name=item_id, scoring_min_participants=24, scoring_min_ideas=150) for item_id in REFERENCES]
        db.add_all(items)
        db.flush()
        for item in items:
            specs = REFERENCES[item.id]
            plan = plan_reference(item.id, [])
            insert_reference(db, item, plan, embed_texts([r["name"] for r in specs]))
            report = populate(db, **corpus_options(item.id))
            assert report["created"] == 15
            assert report["synthetic_originality_distribution"] == {0: 117, 1: 29, 2: 4}
            assert item_is_ready_for_scoring(db, item)
        db.commit()
        assert db.scalar(select(func.count()).select_from(Participant)) == 15
        assert db.scalar(select(func.count()).select_from(ResponseIdea)) == 450
        for response in db.scalars(select(Response)):
            assert response.data_source == "SYNTHETIC"
            assert response.fluency == response.flexibility == 10
            assert response.scoring_status.value == "FINAL"
            assert response.scoring_meta["frequency_basis"]["synthetic_idea_count"] == 150
        for item in items:
            assert populate(db, **corpus_options(item.id))["created"] == 0
            codes = db.scalars(select(ItemCode).where(ItemCode.item_id == item.id)).all()
            assert all(match is not None for _, match in plan_reference(item.id, codes))
        assert db.scalar(select(func.count()).select_from(Response)) == 45
        monkeypatch.setattr(settings, "survey_data_source", "SURVEY")
        for item in items:
            assert qualifying_idea_count(db, item.id) == 0
            assert not item_is_ready_for_scoring(db, item)
