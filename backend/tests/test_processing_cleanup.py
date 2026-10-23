"""Hồi quy refactor: nguồn mapping chuẩn, audit, dọn tạm và bảo toàn migration."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models.models import Item, Participant, PipelineAudit, Response, ResponseIdea, ResponseScoringStatus, SurveySession
from app.pipeline.codebook_service import current_mapping, mapping_diagnostics
from scripts.prune_pipeline_storage import prune_storage


def test_mapping_reads_idea_rows_and_diagnostics_reads_referenced_audit():
    """Cache JSON cũ không được lấn át ý thật; chi tiết LLM chỉ lưu một lần ở audit."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Item(id="item", name="Đũa"), Participant(id="person")])
        row = Response(id="response", participant_id="person", item_id="item", raw_input="gõ nhịp",
                       mapping={"ideas": []}, mapping_meta={"latest_audit_id": "audit"})
        db.add(row)
        db.add_all([
            ResponseIdea(id="idea", response_id=row.id, original="gõ nhịp", normalized="gõ nhịp", mapping_status="VALID"),
            PipelineAudit(id="audit", item_id="item", response_id=row.id, event="PIPELINE_ATTEMPT",
                          payload={"code_curator": {"stage": "code_curator", "usage": {"total_tokens": 30}}}),
        ])
        db.commit()
        assert current_mapping(row)["ideas"][0]["idea_id"] == "idea"
        assert mapping_diagnostics(row)["code_curator"]["usage"]["total_tokens"] == 30
        assert row.mapping == {"ideas": []}


def test_prune_storage_keeps_latest_diagnostics_and_final_score_basis():
    """Dry-run không sửa DB; apply chỉ dọn tạm, giữ phiên có bài và snapshot FINAL."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=100)
    with Session(engine) as db:
        db.add_all([Item(id="item", name="Đũa"), Participant(id="person")])
        row = Response(id="final", participant_id="person", item_id="item", raw_input="gõ nhịp",
                       survey_session_id="used", mapping={}, scoring={"fluency": 1},
                       scoring_status=ResponseScoringStatus.FINAL, scored_at=old,
                       scoring_meta={"mapping_snapshot": {"ideas": []}, "frequency_basis": {"count": 10}},
                       mapping_meta={"latest_audit_id": "latest"}, mapping_checkpoint={"extraction": "temporary"})
        db.add(row)
        for key in ["used", "abandoned"]:
            db.add(SurveySession(id=key, participant_id="person", item_id="item", started_at=old,
                                 deadline_at=old + timedelta(seconds=180)))
        for key, event in [("latest", "PIPELINE_ATTEMPT"), ("obsolete", "PIPELINE_ATTEMPT"), ("decision", "MAPPING_COMMIT")]:
            db.add(PipelineAudit(id=key, item_id="item", response_id=row.id, event=event, created_at=old, payload={}))
        db.commit()
        frozen = (deepcopy(row.scoring), deepcopy(row.scoring_meta), row.scored_at)
        counts = prune_storage(db, before=now - timedelta(days=90))
        assert counts == {"technical_audits": 1, "abandoned_sessions": 1, "final_checkpoints": 1, "applied": False}
        assert db.get(PipelineAudit, "obsolete") is not None
        prune_storage(db, before=now - timedelta(days=90), apply=True)
        db.expire_all()
        assert db.get(PipelineAudit, "obsolete") is None
        assert db.get(PipelineAudit, "latest") is not None
        assert db.get(PipelineAudit, "decision") is not None
        assert db.get(SurveySession, "used") is not None
        assert db.get(SurveySession, "abandoned") is None
        assert row.mapping_checkpoint == {}
        assert (row.scoring, row.scoring_meta, row.scored_at) == frozen


def test_cleanup_migrations_preserve_existing_rows_and_dirty_flags():
    """Nâng/hạ schema trên DB riêng phải giữ nguyên bài, căn cứ và cờ đang chờ."""
    def load(filename):
        from importlib.util import module_from_spec, spec_from_file_location
        from pathlib import Path
        spec = spec_from_file_location(filename, Path(__file__).parents[1] / "alembic/versions" / filename)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    first = load("c0d2e4f6a891_simplify_processing_state.py")
    second = load("c1e3f5a7b902_defer_centroid_refresh.py")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            second.downgrade()
            first.downgrade()
            connection.execute(text("INSERT INTO items (id,name,description,calibration_status,scoring_min_participants,scoring_min_ideas,codebook_epoch,scores_dirty) VALUES ('old','Đũa','','COLLECTING',24,150,0,1)"))
            first.upgrade()
            second.upgrade()
        assert connection.execute(text("SELECT calibration_dirty FROM items WHERE id='old'")).scalar_one() == 1
        assert "centroid_dirty" in {column["name"] for column in inspect(connection).get_columns("item_codes")}
        assert "ix_responses_worker_queue" in {index["name"] for index in inspect(connection).get_indexes("responses")}
