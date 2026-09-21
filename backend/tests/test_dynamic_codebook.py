import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.models import (
    Item,
    ItemCode,
    Participant,
    Response,
    ResponseIdea,
)
from app.pipeline.codebook_service import (
    list_curator_codes,
    originality_for_response,
    persist_mapping,
    qualifying_response_count,
    refresh_item_scoring_state,
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


def _response(participant_id: str, item_id: str) -> Response:
    return Response(
        participant_id=participant_id,
        item_id=item_id,
        raw_input="làm dấu trang",
        mapping={},
        scoring={},
    )


def test_repeat_responses_are_all_qualifying_data():
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
        assert qualifying_response_count(db, item.id) == 2


def test_item_stays_active_when_repeat_response_arrives():
    """Response mới thay đổi tần suất realtime nhưng không tạo thêm trạng thái trung gian."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(
            id="dua",
            name="Đũa",
            description="Đôi đũa",
            scoring_min_participants=1,
            scoring_min_responses=1,
        )
        db.add_all([participant, item])
        db.flush()

        db.add(_response(participant.id, item.id))
        db.flush()
        assert refresh_item_scoring_state(db, item) is True
        assert item.calibration_status.value == "ACTIVE"

        db.add(_response(participant.id, item.id))
        db.flush()
        assert refresh_item_scoring_state(db, item) is False
        assert item.calibration_status.value == "ACTIVE"


def test_item_becomes_active_only_after_both_thresholds_are_reached():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(
            id="chai",
            name="Chai nhựa",
            description="Một chai nhựa",
            scoring_min_participants=2,
            scoring_min_responses=2,
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
        assert refresh_item_scoring_state(db, item) is False
        assert item.calibration_status.value == "COLLECTING"

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

        assert refresh_item_scoring_state(db, item) is True
        assert item.calibration_status.value == "ACTIVE"


def test_realtime_frequency_uses_idea_share_not_submission_share():
    """Một lượt có nhiều ý phải đóng góp từng ý vào mẫu số theo công thức AUT."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(
            id="chai",
            name="Chai nhựa",
            description="Một chai nhựa",
            scoring_min_participants=2,
            scoring_min_responses=2,
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

        _, _, _, _, basis = originality_for_response(db, first)
        frequencies = {
            row["code_id"]: row["frequency"] for row in basis["code_frequencies"]
        }
        assert frequencies[code_a.id] == pytest.approx(2 / 3)
        assert frequencies[code_b.id] == pytest.approx(1 / 3)
        assert sum(frequencies.values()) == pytest.approx(1.0)


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
