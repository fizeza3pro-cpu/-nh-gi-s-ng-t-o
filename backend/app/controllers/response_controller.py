"""Tiếp nhận bài vào hàng đợi và đọc kết quả; worker chịu trách nhiệm xử lý."""
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import settings
from app.pipeline.codebook_service import current_mapping
from app.models.models import (Item as ItemModel, Participant as ParticipantModel, Response as ResponseModel,
    ResponseScoringStatus, ItemCalibrationStatus, SurveySession)
from app.schemas.schemas import (Item, MappingResult, ScoringResult, ScoreRequest, ScoreResponse, ResponseSummary)


def _status_message(status: ResponseScoringStatus) -> str:
    return {
        ResponseScoringStatus.COLLECTING: (
            "Hệ thống hiện đang trong quá trình thu thập dữ liệu. Câu trả lời của bạn là mảnh ghép quan trọng giúp hoàn thiện bộ dữ liệu của chúng tôi."
        ),
        ResponseScoringStatus.PENDING_REVIEW: (
            "Một số ý cần AI đối chiếu lại. Dữ liệu đã được giữ nguyên và chưa bị tính là 0."
        ),
        ResponseScoringStatus.PROVISIONAL: (
            "Điểm tạm thời đang chờ bộ dữ liệu nghiên cứu được chốt."
        ),
        ResponseScoringStatus.FINAL: "Điểm đã được chốt theo mẫu dữ liệu tại thời điểm chấm và không thay đổi khi có bài mới.",
        ResponseScoringStatus.EXCLUDED: "Lượt này bị loại khỏi dữ liệu theo quyết định quản trị.",
    }[status]



def _to_response(row: ResponseModel) -> ScoreResponse:
    scoring_pending = (row.processing_state == "DONE" and row.scoring_status == ResponseScoringStatus.COLLECTING
                       and row.item.calibration_status == ItemCalibrationStatus.ACTIVE and not row.scoring
                       and row.data_source == settings.survey_data_source)
    resolving = (row.scoring_status == ResponseScoringStatus.PENDING_REVIEW
                 and row.resolution_attempts < settings.resolver_max_attempts and row.processing_state != "FAILED")
    if row.scoring_status in {ResponseScoringStatus.FINAL, ResponseScoringStatus.EXCLUDED}:
        result_state = row.scoring_status.value
    elif row.processing_state == "FAILED":
        result_state = "FAILED"
    elif row.processing_state == "QUEUED":
        result_state = "QUEUED"
    elif row.processing_state == "SCORING" or scoring_pending:
        result_state = "SCORING"
    elif resolving:
        result_state = "RESOLVING"
    elif row.processing_state == "RUNNING":
        result_state = "MAPPING"
    elif row.scoring_status == ResponseScoringStatus.PENDING_REVIEW:
        result_state = "REVIEW"
    else:
        result_state = "COLLECTING"
    return ScoreResponse(
        result_state=result_state,
        needs_processing=result_state in {"QUEUED", "MAPPING", "RESOLVING", "SCORING"},
        response_id=row.id,
        item=Item(id=row.item.id, name=row.item.name, description=row.item.description),
        raw_input=row.raw_input,
        mapping=MappingResult.model_validate(
            (row.scoring_meta or {}).get("mapping_snapshot") or current_mapping(row)
            if row.scoring_status == ResponseScoringStatus.FINAL else current_mapping(row)
        ),
        scoring=ScoringResult.model_validate(row.scoring) if row.scoring else None,
        scores_stale=False,
        scoring_pending=scoring_pending,
        scoring_status=row.scoring_status.value,
        processing_state=row.processing_state,
        resolution_pending=resolving,
        status_message=(
            "Bài đã được lưu; hệ thống đang chấm. Bạn có thể đóng trang và xem lại trong lịch sử."
            if row.processing_state in {"QUEUED", "RUNNING", "SCORING"}
            else "Bài đã lưu nhưng xử lý chưa thành công. Vui lòng liên hệ quản trị viên để thử lại."
            if row.processing_state == "FAILED"
            else "AI chưa đủ căn cứ phân loại một số ý sau các lượt đối chiếu. Bài được giữ nguyên; các ý này chưa bị tính là 0."
            if row.scoring_status == ResponseScoringStatus.PENDING_REVIEW and row.resolution_attempts >= settings.resolver_max_attempts
            else _status_message(row.scoring_status)
        ),
    )



def _same_submission(row: ResponseModel, req: ScoreRequest) -> bool:
    """Hai cách chia ô có thể có cùng raw nối dòng nhưng vẫn là hai payload khác."""
    return row.item_id == req.item_id and (
        row.input_lines == req.responses if row.input_lines else row.raw_input == req.raw_input
    )



def _enqueue_response(db: Session, req: ScoreRequest, participant: ParticipantModel) -> ScoreResponse:
    """Commit bài thô trước LLM để đóng trang vẫn giữ được lịch sử."""
    item = db.scalar(select(ItemModel).where(ItemModel.id == req.item_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    # Cùng khóa với cập nhật nhóm để bài đầu và hồ sơ không vượt nhau.
    db.scalar(select(ParticipantModel).where(ParticipantModel.id == participant.id).with_for_update())
    raw = "\n".join(req.responses).strip()
    request_id = str(req.request_id) if req.request_id else str(uuid.uuid4())
    if req.request_id:
        existing = db.scalar(
            select(ResponseModel).where(
                ResponseModel.participant_id == participant.id,
                ResponseModel.request_id == request_id,
            )
        )
        if existing is not None:
            if not _same_submission(existing, req):
                raise HTTPException(status_code=409, detail="Mã gửi bài đã được dùng cho nội dung khác.")
            return _to_response(existing)
    session = None
    if req.survey_session_id:
        session = db.scalar(select(SurveySession).where(SurveySession.id == str(req.survey_session_id)).with_for_update())
        if session is None or session.participant_id != participant.id or session.item_id != req.item_id:
            raise HTTPException(status_code=403, detail="Phiên làm bài không hợp lệ.")
        already = db.scalar(select(ResponseModel).where(ResponseModel.survey_session_id == session.id))
        if already:
            if not _same_submission(already, req):
                raise HTTPException(status_code=409, detail="Phiên này đã nộp nội dung khác.")
            return _to_response(already)
        deadline = session.deadline_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > deadline + timedelta(seconds=settings.survey_grace_seconds):
            raise HTTPException(status_code=409, detail={
                "code": "SURVEY_SESSION_EXPIRED",
                "message": "Đã quá thời gian nhận bài của phiên. Bản nháp vẫn còn trên thiết bị.",
            })
        session.submitted_at = datetime.now(timezone.utc)
    elif settings.survey_session_required:
        raise HTTPException(status_code=400, detail="Cần bắt đầu phiên 3 phút trước khi nộp bài.")
    pending = db.scalars(select(ResponseModel.id).where(
        ResponseModel.participant_id == participant.id,
        ResponseModel.processing_state.in_(["QUEUED", "RUNNING", "SCORING"]),
    ).limit(settings.max_pending_responses_per_participant)).all()
    if len(pending) >= settings.max_pending_responses_per_participant:
        raise HTTPException(status_code=429, detail="Bạn đang có nhiều bài chờ xử lý. Hãy chờ hoàn tất rồi gửi lại.", headers={"Retry-After": "30"})
    row = ResponseModel(
        id=str(uuid.uuid4()),
        participant_id=participant.id,
        item_id=item.id,
        request_id=request_id,
        raw_input=raw,
        input_lines=req.responses,
        data_source=settings.survey_data_source,
        survey_session_id=session.id if session else None,
        mapping={"ideas": []},
        scoring={},
        processing_state="QUEUED",
        scoring_status=ResponseScoringStatus.COLLECTING,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not req.request_id:
            raise
        existing = db.scalar(
            select(ResponseModel).where(
                ResponseModel.participant_id == participant.id,
                ResponseModel.request_id == request_id,
            )
        )
        if existing is None:
            raise
        if not _same_submission(existing, req):
            raise HTTPException(status_code=409, detail="Mã gửi bài đã được dùng cho nội dung khác.")
        return _to_response(existing)
    db.refresh(row)
    return _to_response(row)



def create_response(db: Session, req: ScoreRequest, participant: ParticipantModel) -> ScoreResponse:
    """Trả mã bài sau commit; mọi lượt xử lý đều đi qua worker."""
    queued = _enqueue_response(db, req, participant)
    # Request gửi lại cũng phải nhả khóa trước khi trả kết quả.
    db.commit()
    return queued


def get_response_detail(db: Session, response_id: str, participant_id: str) -> ScoreResponse:
    row = db.get(ResponseModel, response_id)
    if row is None or row.participant_id != participant_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả.")
    return _to_response(row)



def list_responses(db: Session) -> list[ResponseSummary]:
    """Trả toàn bộ lượt làm; route gọi hàm này bắt buộc đã qua guard admin."""
    rows = db.scalars(select(ResponseModel).order_by(ResponseModel.created_at.desc())).all()
    return [
        ResponseSummary(
            response_id=row.id,
            created_at=row.created_at.isoformat() if row.created_at else "",
            item_id=row.item_id,
            item_name=row.item.name if row.item else "",
            fluency=row.fluency,
            flexibility=row.flexibility,
            originality=row.originality,
            elaboration=row.elaboration,
            scoring_status=row.scoring_status.value,
            processing_state=row.processing_state,
        )
        for row in rows
    ]
def list_participant_responses(db: Session, participant_id: str) -> list[ResponseSummary]:
    """Trả lịch sử của đúng participant đã được xác thực bằng header trình duyệt."""
    rows = db.scalars(
        select(ResponseModel)
        .where(ResponseModel.participant_id == participant_id)
        .order_by(ResponseModel.created_at.desc())
    ).all()
    return [
        ResponseSummary(
            response_id=row.id,
            created_at=row.created_at.isoformat() if row.created_at else "",
            item_id=row.item_id,
            item_name=row.item.name if row.item else "",
            fluency=row.fluency,
            flexibility=row.flexibility,
            originality=row.originality,
            elaboration=row.elaboration,
            scoring_status=row.scoring_status.value,
            processing_state=row.processing_state,
        )
        for row in rows
    ]
