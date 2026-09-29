"""Bộ mã tham chiếu không được tự tạo dữ liệu hay tần suất khảo sát."""
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.db import Base
from app.models.models import Item, ItemCode, Response, ResponseIdea, PipelineAudit
from app.pipeline.shell_reference import SHELL_REFERENCE, plan_shell_reference
from app.pipeline.embedding import embed_texts
from app.pipeline.codebook_service import list_curator_codes
from app.schemas.schemas import FunctionalSignature
from app.pipeline.dynamic_mapping import normalize_code_name
from scripts.import_shell_reference import insert_reference


def test_reference_has_distinct_boundaries_and_complete_signatures():
    assert len({entry["key"] for entry in SHELL_REFERENCE}) == len(SHELL_REFERENCE)
    for entry in SHELL_REFERENCE:
        signature = FunctionalSignature.model_validate(entry["functional_signature"])
        assert signature.goal and signature.object_role and signature.mechanism
        assert entry["inclusion_rules"] and entry["exclusion_rules"]
        assert entry["illustrative_examples"]


def test_import_is_idempotent_visible_and_adds_no_observations():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại rỗng")
        db.add(item)
        db.flush()
        batch = embed_texts([entry["name"] for entry in SHELL_REFERENCE])
        created = insert_reference(db, item, plan_shell_reference([]), batch)
        db.commit()
        assert len(list_curator_codes(db, item.id)) == len(SHELL_REFERENCE)
        rows = db.scalars(select(ItemCode)).all()
        assert all(not row.positive_examples and row.centroid_count == 0 and not row.admin_locked for row in rows)
        assert db.scalar(select(func.count()).select_from(Response)) == 0
        assert db.scalar(select(func.count()).select_from(ResponseIdea)) == 0
        assert insert_reference(db, item, plan_shell_reference(rows), embed_texts([])) == []
        assert db.scalar(select(func.count()).select_from(ItemCode)) == len(created)
        assert db.scalar(select(func.count()).select_from(PipelineAudit)) == 1
        assert item.codebook_epoch == 1


def test_existing_alias_is_reused_without_rewriting_observations():
    from types import SimpleNamespace
    from app.models.models import CodeValidationStatus, CodeMaturityStatus
    import pytest

    entry = SHELL_REFERENCE[0]
    code = SimpleNamespace(id="existing", normalized_name=normalize_code_name(entry["existing_names"][0]),
                           validation_status=CodeValidationStatus.ACCEPTED,
                           maturity_status=CodeMaturityStatus.ACTIVE,
                           positive_examples=["Ví dụ đã quan sát"], centroid_count=4)
    plan = plan_shell_reference([code])
    assert plan[0][1] is code
    assert code.positive_examples == ["Ví dụ đã quan sát"] and code.centroid_count == 4
    code.validation_status = CodeValidationStatus.REJECTED
    with pytest.raises(ValueError, match="không tự kích hoạt lại"):
        plan_shell_reference([code])
