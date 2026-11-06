"""Rà soát chỉ đọc: phát hiện tín hiệu trùng mà không tự kết luận/gộp."""
from copy import deepcopy

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models.models import Item, ItemCode, Participant, Response, ResponseIdea
from scripts.inspect_codebook_quality import inspect_codebook_quality


def test_quality_report_finds_shared_function_without_mutating_rows():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Item(id="thread", name="Cuộn chỉ"), Participant(id="p")])
        signatures = [
            {"goal": "buộc, cố định vật thể", "object_role": "dây buộc", "mechanism": "quấn, siết vật"},
            {"goal": "buộc giữ các vật với nhau", "object_role": "dây buộc", "mechanism": "thắt nút"},
        ]
        for index, signature in enumerate(signatures):
            db.add(ItemCode(id=str(index), item_id="thread", name=f"Dây buộc {index}", normalized_name=str(index),
                            description="Dùng cuộn chỉ làm dây buộc", functional_signature=signature,
                            inclusion_rules=["Buộc giữ vật"], exclusion_rules=["Khâu vải khác chức năng"]))
        frozen = {"mapping_snapshot": {"immutable": True}}
        db.add(Response(id="r", item_id="thread", participant_id="p", raw_input="buộc giữ", mapping={},
                        scoring_status="FINAL", scoring_meta=deepcopy(frozen)))
        db.add(ResponseIdea(id="i", response_id="r", code_id="0", original="buộc giữ", normalized="buộc giữ", mapping_status="VALID"))
        db.commit()
        before = [deepcopy(dict(row)) for row in db.execute(select(ItemCode.__table__)).mappings()]
        report = inspect_codebook_quality(db)
        pairs = report["items"][0]["suspected_overlaps"]
        assert pairs and not pairs[0]["confirmed_duplicate"]
        assert "SHARED_GOAL_AND_ROLE_WORDS" in pairs[0]["signals"]
        assert pairs[0]["left"]["member_examples"] == ["buộc giữ"]
        assert report["external_api_calls"] == 0 and report["read_only"]
        assert [dict(row) for row in db.execute(select(ItemCode.__table__)).mappings()] == before
        assert db.get(Response, "r").scoring_meta == frozen
        assert not db.dirty and not db.deleted and not db.new


def test_quality_report_distinguishes_missing_and_conflicting_boundaries():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Item(id="item", name="Đồ vật"))
        db.add(ItemCode(id="bad", item_id="item", name="Mã chưa rõ", normalized_name="bad",
                        functional_signature={"goal": "trang trí"},
                        inclusion_rules=["Nhận vật trang trí"], exclusion_rules=["Nhận vật trang trí"]))
        db.commit()
        issues = inspect_codebook_quality(db, "item")["items"][0]["incomplete_or_conflicting_boundaries"]
        assert set(issues[0]["missing_fields"]) == {"object_role", "mechanism"}
        assert issues[0]["identical_inclusion_exclusion"]
