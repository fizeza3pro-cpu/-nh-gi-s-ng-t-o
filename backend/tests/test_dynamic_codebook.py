import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.config import settings
from app.models.models import (
    CodebookVersionCode,
    Item,
    ItemCode,
    Participant,
    Response,
    ResponseIdea,
)
from app.pipeline.codebook_service import (
    eligible_response_count,
    list_curator_codes,
    maybe_refresh_codebook,
    persist_mapping,
)
from app.schemas.schemas import (
    CuratorDecision,
    CuratorResult,
    ExtractedIdea,
    IdeaExtractionResult,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _response(participant_id: str, item_id: str, eligible: bool = True) -> Response:
    return Response(
        participant_id=participant_id,
        item_id=item_id,
        raw_input="làm dấu trang",
        mapping={},
        scoring={},
        calibration_eligible=eligible,
    )


def test_repeat_responses_are_all_calibration_samples():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="dua", name="Đũa", description="Đôi đũa")
        db.add_all([participant, item])
        db.commit()

        db.add_all([
            _response(participant.id, item.id),
            _response(participant.id, item.id),
        ])
        db.commit()
        assert eligible_response_count(db, item.id) == 2


def test_repeat_response_can_refresh_frequency_snapshot(monkeypatch):
    """Lượt làm lại thay đổi phân bố nên cũng phải thúc đẩy chu kỳ đóng snapshot."""
    engine = _engine()
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "codebook_refresh_interval", 1)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(
            id="dua",
            name="Đũa",
            description="Đôi đũa",
            calibration_min_participants=1,
            originality_min_participants=2,
        )
        db.add_all([participant, item])
        db.flush()

        db.add(_response(participant.id, item.id))
        db.flush()
        first_version, first_activation = maybe_refresh_codebook(db, item)
        assert first_activation is True
        assert first_version is not None
        assert first_version.response_count == 1

        db.add(_response(participant.id, item.id))
        db.flush()
        second_version, refreshed = maybe_refresh_codebook(db, item)
        assert refreshed is True
        assert second_version is not None
        assert second_version.version == 2
        assert second_version.response_count == 2
        assert second_version.participant_count == 1


def test_reaching_threshold_creates_an_immutable_frequency_snapshot():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(
            id="chai",
            name="Chai nhựa",
            description="Một chai nhựa",
            calibration_min_participants=2,
            originality_min_participants=4,
        )
        p1, p2 = Participant(id=str(uuid.uuid4())), Participant(id=str(uuid.uuid4()))
        code = ItemCode(
            item_id=item.id,
            name="Dụng cụ tưới",
            normalized_name="dung cu tuoi",
            confidence=0.95,
        )
        db.add_all([item, p1, p2, code])
        db.flush()

        first = _response(p1.id, item.id)
        db.add(first)
        db.flush()
        db.add(
            ResponseIdea(
                response_id=first.id,
                code_id=code.id,
                original="tưới cây",
                normalized="Dùng làm bình tưới cây",
                mapping_status="VALID",
                confidence=0.95,
            )
        )
        db.flush()
        assert maybe_refresh_codebook(db, item) == (None, False)

        second = _response(p2.id, item.id)
        db.add(second)
        db.flush()
        db.add(
            ResponseIdea(
                response_id=second.id,
                code_id=code.id,
                original="tưới hoa",
                normalized="Dùng làm bình tưới hoa",
                mapping_status="VALID",
                confidence=0.95,
            )
        )
        db.flush()

        version, first_activation = maybe_refresh_codebook(db, item)
        db.flush()
        assert version is not None
        assert first_activation is True
        assert version.version == 1
        snapshot = db.scalar(
            select(CodebookVersionCode).where(CodebookVersionCode.version_id == version.id)
        )
        assert snapshot is not None
        assert snapshot.response_count == 2
        assert snapshot.participant_count == 2
        assert snapshot.frequency == 1.0


def test_snapshot_frequency_uses_idea_share_not_submission_share():
    """Một lượt có nhiều ý phải đóng góp từng ý vào mẫu số theo công thức AUT."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(
            id="chai",
            name="Chai nhựa",
            description="Một chai nhựa",
            calibration_min_participants=2,
            originality_min_participants=4,
        )
        p1, p2 = Participant(id=str(uuid.uuid4())), Participant(id=str(uuid.uuid4()))
        code_a = ItemCode(
            item_id=item.id,
            name="Bình tưới",
            normalized_name="binh tuoi",
            confidence=0.95,
        )
        code_b = ItemCode(
            item_id=item.id,
            name="Chậu cây",
            normalized_name="chau cay",
            confidence=0.95,
        )
        db.add_all([item, p1, p2, code_a, code_b])
        db.flush()

        first = _response(p1.id, item.id)
        second = _response(p2.id, item.id)
        db.add_all([first, second])
        db.flush()
        db.add_all(
            [
                ResponseIdea(
                    response_id=first.id,
                    code_id=code_a.id,
                    original="tưới cây",
                    normalized="Dùng làm bình tưới cây",
                    mapping_status="VALID",
                    confidence=0.95,
                ),
                ResponseIdea(
                    response_id=first.id,
                    code_id=code_b.id,
                    original="trồng cây",
                    normalized="Dùng làm chậu trồng cây",
                    mapping_status="VALID",
                    confidence=0.95,
                ),
                ResponseIdea(
                    response_id=second.id,
                    code_id=code_a.id,
                    original="tưới hoa",
                    normalized="Dùng làm bình tưới hoa",
                    mapping_status="VALID",
                    confidence=0.95,
                ),
                ResponseIdea(
                    response_id=second.id,
                    code_id=code_a.id,
                    original="có thể là bình tưới",
                    normalized="Có thể dùng làm bình tưới",
                    mapping_status="VALID",
                    confidence=0.50,
                    reason="AI chưa chắc ý này khớp với mã bình tưới.",
                ),
            ]
        )
        db.flush()

        version, _ = maybe_refresh_codebook(db, item)
        assert version is not None
        snapshots = {
            row.code_id: row
            for row in db.scalars(
                select(CodebookVersionCode).where(
                    CodebookVersionCode.version_id == version.id
                )
            ).all()
        }
        assert snapshots[code_a.id].idea_count == 2
        assert snapshots[code_a.id].frequency == pytest.approx(2 / 3)
        assert snapshots[code_b.id].idea_count == 1
        assert snapshots[code_b.id].frequency == pytest.approx(1 / 3)
        assert sum(row.frequency for row in snapshots.values()) == pytest.approx(1.0)


def test_curator_nullable_optional_text_is_normalized():
    """Output JSON `null` của LLM không được làm hỏng toàn bộ lượt submit."""
    result = CuratorResult.model_validate(
        {
            "decisions": [
                {
                    "idea_index": 3,
                    "decision": "MATCH_EXISTING",
                    "existing_code_id": "code-1",
                    "code_name": None,
                    "code_description": None,
                    "confidence": 0.94,
                    "reason": None,
                }
            ]
        }
    )

    assert result.decisions[0].code_description == ""
    assert result.decisions[0].reason == ""


def test_extraction_object_guard_rejects_another_object():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="day_thung", name="Dây thừng", description="Dùng để buộc")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()

        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="Gấp giấy báo để bọc quà",
                    normalized="Dùng giấy báo bọc quà",
                    status="VALID",
                    uses_target_object=False,
                    object_used="Giấy báo",
                    target_object_role="",
                )
            ]
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="CREATE_NEW",
                    code_name="Bọc quà bằng giấy báo",
                    code_description="Dùng giấy báo để bọc quà",
                    confidence=0.99,
                )
            ]
        )

        mapping, _ = persist_mapping(
            db,
            item=item,
            response=response,
            extraction=extraction,
            curator=curator,
        )
        idea = db.scalar(select(ResponseIdea).where(ResponseIdea.response_id == response.id))
        assert mapping.ideas[0].status == "INVALID"
        assert idea.curator_decision == "EXTRACTION_OBJECT_GUARD"
        assert db.scalars(select(ItemCode)).all() == []


def test_curator_cannot_create_code_for_another_object():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="day_thung", name="Dây thừng", description="Dùng để buộc")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()

        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="Làm dây phơi",
                    normalized="Dùng làm dây phơi",
                    status="VALID",
                    uses_target_object=True,
                    object_used="Dây thừng",
                    target_object_role="Chịu lực để treo quần áo",
                )
            ]
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="CREATE_NEW",
                    code_name="Bọc quà bằng giấy báo",
                    code_description="Dùng giấy báo để bọc quà",
                    target_object_confirmed=True,
                    target_object_role="Chịu lực",
                    confidence=0.99,
                )
            ]
        )

        mapping, _ = persist_mapping(
            db,
            item=item,
            response=response,
            extraction=extraction,
            curator=curator,
        )
        rejected = db.scalar(select(ItemCode))
        assert mapping.ideas[0].status == "INVALID"
        assert rejected.validation_status.value == "REJECTED"


def test_curator_does_not_receive_off_object_existing_codes():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(id="day_thung", name="Dây thừng", description="Dùng để buộc")
        db.add_all(
            [
                item,
                ItemCode(
                    item_id=item.id,
                    name="Bọc quà bằng giấy báo",
                    normalized_name="boc qua bang giay bao",
                    description="Dùng giấy báo để bọc quà",
                ),
                ItemCode(
                    item_id=item.id,
                    name="Làm dây phơi bằng dây thừng",
                    normalized_name="lam day phoi bang day thung",
                    description="Dùng dây thừng chịu lực để treo quần áo",
                ),
            ]
        )
        db.flush()

        codes = list_curator_codes(db, item.id)
        assert [code["name"] for code in codes] == ["Làm dây phơi bằng dây thừng"]
