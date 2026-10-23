"""Kiểm tra báo cáo không trộn mẫu, không nhân trọng số của người nộp nhiều lượt."""

import math
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.controllers.research_report_controller import _adjust_holm, _compare, get_research_report
from app.controllers.admin_controller import _ai_group_stats
from app.core.deps import require_admin
from app.db import Base, get_db
from app.main import app
from app.models.models import (
    CodeValidationStatus, Item, ItemCode, Participant, Response, ResponseIdea, ResponseScoringStatus,
)


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(settings, "survey_data_source", "PILOT")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _response(db, participant, item, value=0, **kwargs):
    row = Response(
        participant_id=participant.id, item_id=item.id, raw_input="Câu trả lời",
        mapping={"ideas": []}, scoring={"fluency": value, "flexibility": value, "originality": value, "elaboration": value},
        fluency=value, flexibility=value, originality=value, elaboration=value,
        scoring_status=kwargs.pop("scoring_status", ResponseScoringStatus.FINAL), **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def _idea(db, response, status, code=None):
    db.add(ResponseIdea(response_id=response.id, mapping_status=status, code_id=code.id if code else None,
                        original="Ý tưởng", normalized="Ý tưởng"))


def test_report_matches_dashboard_weights_people_equally_and_excludes_other_samples(db):
    a, b = Item(id="a", name="Đũa"), Item(id="b", name="Vỏ sò")
    low1, low2 = Participant(ai_usage_group="LOW"), Participant(ai_usage_group="LOW")
    high1, high2 = Participant(ai_usage_group="HIGH"), Participant(ai_usage_group="HIGH")
    unknown = Participant()
    db.add_all([a, b, low1, low2, high1, high2, unknown])
    db.flush()
    shared = ItemCode(item_id=a.id, name="Chung", normalized_name="chung")
    low_only = ItemCode(item_id=a.id, name="Riêng", normalized_name="rieng")
    unused = ItemCode(item_id=a.id, name="Chưa dùng", normalized_name="chua dung")
    rejected = ItemCode(item_id=a.id, name="Bị loại", normalized_name="bi loai", validation_status=CodeValidationStatus.REJECTED)
    db.add_all([shared, low_only, unused, rejected])
    db.flush()
    first = _response(db, low1, a, 0)
    _idea(db, first, "VALID", shared)
    _idea(db, first, "VALID", low_only)
    _idea(db, first, "INVALID")
    _idea(db, first, "DUPLICATE")
    _response(db, low1, a, 8)
    _response(db, low1, b, 8)
    _response(db, low2, a, 2)
    high = _response(db, high1, a, 8)
    _idea(db, high, "VALID", shared)
    _response(db, high2, a, 10)
    pending = _response(db, unknown, a, scoring_status=ResponseScoringStatus.PENDING_REVIEW)
    _idea(db, pending, "VALID")
    _idea(db, pending, "VALID", rejected)
    _idea(db, pending, "LEGACY")
    excluded = _response(db, low1, a, 100, scoring_status=ResponseScoringStatus.EXCLUDED)
    _idea(db, excluded, "VALID", unused)
    _response(db, low1, a, 100, processing_state="QUEUED")
    _response(db, low1, a, 100, processing_state="FAILED")
    synthetic = _response(db, high1, a, 100, data_source="SYNTHETIC")
    _idea(db, synthetic, "VALID", unused)
    _response(db, high1, a, 100, data_source="SURVEY")
    db.commit()

    report = get_research_report(db)
    assert report.sample.submitted_responses == 10
    assert report.sample.analyzed_responses == 7
    assert report.sample.final_scored_responses == 6
    assert report.sample.excluded_responses == 1
    assert report.sample.unfinished_responses == 1
    assert report.sample.failed_responses == 1
    assert report.sample.other_source_responses == 2
    assert report.sample.ungrouped_responses == 1
    assert report.totals.participant_count == 5
    assert report.totals.total_ideas == 8
    assert report.totals.valid_ideas == 5
    assert report.totals.invalid_ideas == 1
    assert report.totals.duplicate_ideas == 1
    assert report.totals.unclassified_ideas == 1
    assert report.totals.pending_code_ideas == 2
    codes = next(row for row in report.object_codes if row.item_id == "a")
    assert (codes.low_code_count, codes.high_code_count, codes.shared_code_count, codes.total_code_count) == (2, 1, 1, 2)
    # Người LOW thứ nhất có (0 + 8 + 8)/3; LOW thứ hai = 2.
    score = report.dimensions[0]
    assert score.low.n == 2
    assert score.low.mean == pytest.approx(11 / 3)
    assert score.low.sem == pytest.approx(5 / 3)
    assert score.high.mean == 9
    assert score.difference == pytest.approx(16 / 3)
    dashboard = _ai_group_stats(db)
    for group, estimate in zip(dashboard, (score.low, score.high)):
        assert group.mean_originality == estimate.mean
        assert group.scored_participant_count == estimate.n
        assert group.submitted_participant_count == 2
        assert group.participant_count == 2
    assert sum(group.final_response_count for group in dashboard) == report.sample.final_scored_responses

    filtered = get_research_report(db, item_id="a")
    assert filtered.dimensions[0].low.mean == 3
    assert len(filtered.object_codes) == 1
    survey = get_research_report(db, data_source="SURVEY")
    assert survey.sample.analyzed_responses == 1
    assert survey.dimensions[0].low.mean is None
    assert survey.dimensions[0].high.mean == 100
    assert not db.dirty


def test_multi_item_filter_is_union_and_counts_people_once(db):
    a, b, c = (Item(id=key, name=key) for key in ("a", "b", "c"))
    person = Participant(ai_usage_group="HIGH")
    never_submitted = Participant(ai_usage_group="HIGH")
    db.add_all([a, b, c, person, never_submitted])
    db.flush()
    for item, value in ((a, 2), (b, 4), (c, 100)):
        _response(db, person, item, value)
    db.commit()
    report = get_research_report(db, item_ids=["a", "b", "a"])
    assert report.item_ids == ["a", "b"]
    assert report.item_id is None
    assert report.sample.submitted_responses == 2
    assert report.sample.final_scored_responses == 2
    assert report.totals.participant_count == 1
    assert report.sample.registered_participants_high == 2
    assert report.sample.submitted_participants_high == 1
    assert report.sample.score_participants_high == 1
    assert report.dimensions[0].high.mean == 3
    assert {row.item_id for row in report.object_codes} == {"a", "b"}


def test_report_keeps_frozen_final_scores_when_new_data_is_dirty(db):
    item = Item(id="a", name="Đũa", calibration_dirty=True)
    person = Participant(ai_usage_group="LOW")
    db.add_all([item, person])
    db.flush()
    _response(db, person, item, 7)
    collecting = _response(db, person, item, scoring_status=ResponseScoringStatus.COLLECTING)
    _idea(db, collecting, "INVALID")
    db.commit()
    report = get_research_report(db)
    assert report.sample.stale_score_responses == 0
    assert report.sample.analyzed_responses == 2
    assert report.totals.invalid_ideas == 1
    assert all(row.low.mean == 7 and row.high.mean is None for row in report.dimensions)
    assert item.calibration_dirty is True
    assert _ai_group_stats(db)[0].scored_participant_count == 1
    assert _ai_group_stats(db)[0].mean_fluency == 7
    assert not db.dirty


def test_welch_and_sem_match_known_sample_and_holm_handles_four_comparisons():
    result = _compare("originality", [1, 2, 3], [4, 5, 6])
    assert result.low.mean == 2
    assert result.low.sd == 1
    assert result.low.sem == pytest.approx(1 / math.sqrt(3))
    assert result.p_value == pytest.approx(0.0213116411)
    rows = [_compare(dimension, [1, 2, 3], [4, 5, 6]) for dimension in ("originality", "flexibility", "fluency", "elaboration")]
    _adjust_holm(rows)
    assert all(row.p_value_holm == pytest.approx(0.0852465644) for row in rows)


def test_postgresql_decimal_averages_are_supported():
    result = _compare("fluency", [Decimal("1"), Decimal("2"), Decimal("3")],
                      [Decimal("4"), Decimal("5"), Decimal("6")])
    assert result.low.sem == pytest.approx(1 / math.sqrt(3))
    assert result.p_value == pytest.approx(0.0213116411)


@pytest.mark.parametrize("low,high", [([], []), ([0], [1, 2]), ([0, 0], [0, 0]), ([1, 1], [3, 3])])
def test_missing_or_constant_samples_do_not_invent_p_values(low, high):
    result = _compare("fluency", low, high)
    assert result.p_value is None
    assert result.test_note
    if len(low) == 1:
        assert result.low.mean == 0
        assert result.low.sem is None


def test_report_route_is_admin_only_and_validates_filters(db):
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            assert client.get("/api/admin/reports/research").status_code in (401, 403)
            app.dependency_overrides[require_admin] = lambda: object()
            response = client.get("/api/admin/reports/research")
            assert response.status_code == 200
            assert response.json()["totals"]["total_ideas"] == 0
            assert client.get("/api/admin/reports/research?data_source=SYNTHETIC").status_code == 422
            assert client.get("/api/admin/reports/research?item_id=missing").status_code == 404
            db.add_all([Item(id="a", name="A"), Item(id="b", name="B"), Item(id="c", name="C")])
            db.commit()
            filtered = client.get("/api/admin/reports/research?item_ids=a&item_ids=b")
            assert filtered.status_code == 200
            assert filtered.json()["item_ids"] == ["a", "b"]
            assert len(filtered.json()["object_codes"]) == 2
            assert client.get("/api/admin/reports/research?item_ids=a&item_ids=missing").status_code == 404
    finally:
        app.dependency_overrides.clear()
