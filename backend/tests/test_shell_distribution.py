"""Kiểm thử phân bố, nguồn mô phỏng và ngưỡng chấm trên DB riêng trong bộ nhớ."""
from collections import Counter
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base
from app.models.models import Item, ItemCode, Response, Participant, ResponseIdea
from app.pipeline.embedding import embed_texts
from app.pipeline.shell_reference import SHELL_REFERENCE, plan_shell_reference
from app.pipeline.codebook_service import qualifying_idea_count, qualifying_participant_count, item_is_ready_for_scoring
from scripts.import_shell_reference import insert_reference
from scripts.seed_shell_distribution import build_corpus, COUNTS, populate


def test_distribution_has_150_distinct_within_response_ideas():
    corpus = build_corpus()
    assert len(corpus) == 15
    assert all(len(bucket) == 10 and len({text for _, text, _ in bucket}) == 10 for bucket in corpus)
    assert Counter(key for bucket in corpus for key, _, _ in bucket) == COUNTS


def test_seed_scores_real_formula_and_is_excluded_from_survey(monkeypatch):
    monkeypatch.setattr(settings, "survey_data_source", "PILOT")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(id="vo_dan", name="Vỏ đạn", scoring_min_participants=24, scoring_min_ideas=150)
        db.add(item)
        db.flush()
        insert_reference(db, item, plan_shell_reference([]), embed_texts([r["name"] for r in SHELL_REFERENCE]))
        report = populate(db)
        db.commit()
        assert report["created"] == 15
        assert db.scalar(select(func.count()).select_from(Participant)) == 5
        assert db.scalar(select(func.count()).select_from(ResponseIdea)) == 150
        assert qualifying_idea_count(db, item.id) == 150
        assert qualifying_participant_count(db, item.id) == 5
        assert item_is_ready_for_scoring(db, item)
        assert set(report["synthetic_originality_distribution"]) == {0, 1, 2}
        for response in db.scalars(select(Response)).all():
            assert response.data_source == "SYNTHETIC"
            assert response.fluency == 10
            assert response.scoring_meta["frequency_basis"]["synthetic_idea_count"] == 150
            assert all(evidence in score["original"] for score in response.scoring["per_idea_scores"]
                       for evidence in score["elaboration_details"].values())
        assert populate(db)["created"] == 0
        assert db.scalar(select(func.count()).select_from(Response)) == 15
        monkeypatch.setattr(settings, "survey_data_source", "SURVEY")
        assert qualifying_idea_count(db, item.id) == 0
        assert not item_is_ready_for_scoring(db, item)
