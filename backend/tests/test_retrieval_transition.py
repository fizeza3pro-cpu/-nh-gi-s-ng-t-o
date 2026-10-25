"""Chuyển vector kỹ thuật không làm thay đổi điểm hoặc mapping đã chốt."""
from copy import deepcopy
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.config import settings
from app.models.models import Item, ItemCode, Participant, Response, ResponseIdea
from app.pipeline.embedding import embedding_model
from scripts.rebuild_retrieval_vectors import rebuild_vectors


def test_additive_migration_preserves_existing_rows(monkeypatch):
    path = Path(__file__).parents[1] / "alembic/versions/c2f4a6b8d013_add_signature_embeddings.py"
    spec = importlib.util.spec_from_file_location("retrieval_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE item_codes (id TEXT PRIMARY KEY, centroid_dirty BOOLEAN, description TEXT)")
        connection.exec_driver_sql("INSERT INTO item_codes VALUES ('code', false, 'same')")
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.upgrade()
        row = connection.exec_driver_sql("SELECT id, centroid_dirty, description, signature_embeddings FROM item_codes").one()
        assert tuple(row) == ("code", 1, "same", "{}")
        module.downgrade()
        assert "signature_embeddings" not in {c["name"] for c in inspect(connection).get_columns("item_codes")}
        assert connection.exec_driver_sql("SELECT description FROM item_codes").scalar() == "same"


def test_backfill_only_updates_vectors_and_requires_new_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "embedding_provider", "local")
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = lambda: Session(engine)
    signature = {"goal": "chứa đồ", "object_role": "vật chứa", "mechanism": "khoang rỗng"}
    with factory() as db:
        db.add_all([Item(id="bag", name="Balo"), Participant(id="p"), ItemCode(id="c", item_id="bag", name="Chứa đồ",
            normalized_name="chua do", description="Balo chứa đồ", functional_signature=signature,
            embedding=[1., 0.], embedding_model="legacy", centroid=[1., 0.], centroid_model="legacy", centroid_count=1)])
        db.add(Response(id="r", item_id="bag", participant_id="p", raw_input="đựng sách", processing_state="DONE",
            scoring_status="FINAL", fluency=1, flexibility=1, scoring={"unchanged": True},
            scoring_meta={"score_policy": "FINAL_FROZEN_V1", "mapping_snapshot": {"frozen": True}}, mapping={"old": True}))
        db.add(ResponseIdea(id="i", response_id="r", code_id="c", original="đựng sách", normalized="đựng sách",
            mapping_status="VALID", functional_signature=signature, mapping_evidence={"old": True},
            embedding=[1., 0.], embedding_model="legacy"))
        db.commit()
        before_response = deepcopy(dict(db.execute(select(Response.__table__)).mappings().one()))
        before_idea = deepcopy(dict(db.execute(select(ResponseIdea.__table__)).mappings().one()))
    dry = rebuild_vectors(factory)
    assert not dry["applied"] and dry["ideas_to_convert"] == 1
    backup = tmp_path / "vectors.json"
    result = rebuild_vectors(factory, apply=True, backup_path=backup)
    assert result["applied"] and result["ideas_updated"] == 1
    with factory() as db:
        assert dict(db.execute(select(Response.__table__)).mappings().one()) == before_response
        after_idea = dict(db.execute(select(ResponseIdea.__table__)).mappings().one())
        for key in before_idea.keys() - {"embedding", "embedding_model"}:
            assert before_idea[key] == after_idea[key]
        assert after_idea["embedding_model"] == embedding_model(None)
        code = db.get(ItemCode, "c")
        assert code.centroid_model == embedding_model(None) and code.centroid_count == 1
        assert code.signature_embeddings["goal"]
    import pytest
    with pytest.raises(FileExistsError):
        rebuild_vectors(factory, apply=True, backup_path=backup)
