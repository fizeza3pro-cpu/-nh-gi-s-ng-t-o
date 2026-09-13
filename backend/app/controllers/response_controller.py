"""Nghiệp vụ nộp bài, xây codebook động và đọc kết quả theo UUID khó đoán."""

import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException
from openai import OpenAI
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.models import (
    CodebookVersion,
    CodeValidationStatus,
    Item as ItemModel,
    ItemCode,
    Participant as ParticipantModel,
    Response as ResponseModel,
    ResponseIdea,
    ResponseScoringStatus,
)
from app.pipeline.codebook_service import (
    create_codebook_version,
    eligible_participant_count,
    list_curator_codes,
    mark_item_for_recalculation,
    maybe_refresh_codebook,
    originality_for_response,
    persist_mapping,
)
from app.pipeline.dynamic_mapping import run_code_curator, run_idea_extraction
from app.pipeline.scoring import run_scoring
from app.schemas.schemas import (
    CuratorDecision,
    CuratorResult,
    ExtractedIdea,
    IdeaExtractionResult,
    Item,
    MappingResult,
    PerIdeaScore,
    ResponseSummary,
    ScoreRequest,
    ScoreResponse,
    ScoringResult,
)


def _client() -> OpenAI:
    if not settings.openrouter_api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY chưa được cấu hình.")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)


def _mock_mapping(
    item: Item, raw: str, existing_codes: list[dict]
) -> tuple[IdeaExtractionResult, CuratorResult]:
    """Mock có cùng contract hai tầng để test không vô tình quay lại code tĩnh."""
    lines = [line.strip() for line in raw.replace(",", "\n").splitlines() if line.strip()][:12]
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                original=line,
                normalized=line,
                status="VALID",
                uses_target_object=True,
                object_used=item.name,
                target_object_role="Đóng vai trò vật thể chính trong công dụng mô phỏng.",
            )
            for line in lines
        ]
    )
    by_name = {code["name"].strip().casefold(): code for code in existing_codes}
    decisions = []
    for index, line in enumerate(lines):
        existing = by_name.get(line.casefold())
        if existing:
            decisions.append(
                CuratorDecision(
                    idea_index=index,
                    decision="MATCH_EXISTING",
                    existing_code_id=existing["id"],
                    target_object_confirmed=True,
                    target_object_role="Dùng đúng đồ vật mục tiêu.",
                    confidence=0.99,
                    reason="[MOCK] Khớp code đã có.",
                )
            )
        else:
            decisions.append(
                CuratorDecision(
                    idea_index=index,
                    decision="CREATE_NEW",
                    code_name=line[:80],
                    code_description=f"[MOCK] Dùng {item.name}: {line[:120]}",
                    target_object_confirmed=True,
                    target_object_role="Dùng đúng đồ vật mục tiêu.",
                    confidence=0.95,
                    reason="[MOCK] Công dụng hợp lệ chưa có trong codebook.",
                )
            )
    return extraction, CuratorResult(decisions=decisions)


def _mock_scoring(
    fluency: int,
    flexibility: int,
    flexibility_codes: list[str],
    per_idea: list[PerIdeaScore],
) -> tuple[ScoringResult, dict]:
    scored = [score.model_copy(update={"elaboration": 2, "note": "[MOCK]"}) for score in per_idea]
    return (
        ScoringResult(
            fluency=fluency,
            flexibility=flexibility,
            flexibility_codes=flexibility_codes,
            originality=sum(score.originality for score in scored),
            elaboration=sum(score.elaboration for score in scored),
            per_idea_scores=scored,
            summary_vi="[MOCK] Điểm tạm được tính từ codebook động.",
        ),
        {"mock": True},
    )


def _needs_curator_retry(curator: CuratorResult, extraction: IdeaExtractionResult) -> bool:
    expected = sum(
        idea.status == "VALID" and idea.uses_target_object for idea in extraction.ideas
    )
    return len(curator.decisions) < expected or any(
        decision.confidence < settings.code_accept_confidence
        or (
            decision.decision != "INVALID"
            and (
                not decision.target_object_confirmed
                or not decision.target_object_role.strip()
            )
        )
        for decision in curator.decisions
    )


def _prefer_confident(first: CuratorResult, second: CuratorResult) -> CuratorResult:
    """Lần hai chỉ ghi đè khi chắc chắn hơn, tránh lấy trung bình làm mất ý hiếm."""
    selected = {decision.idea_index: decision for decision in first.decisions}
    for decision in second.decisions:
        previous = selected.get(decision.idea_index)
        if previous is None or decision.confidence > previous.confidence:
            selected[decision.idea_index] = decision
    return CuratorResult(decisions=list(selected.values()))


def _score_row(db: Session, row: ResponseModel, client: OpenAI | None = None) -> None:
    item_row = row.item
    if not item_row.active_codebook_version_id:
        return
    version = db.get(CodebookVersion, item_row.active_codebook_version_id)
    if version is None:
        return

    fluency, flexibility, flex_codes, per_idea, uses_live = originality_for_response(
        db, row, version
    )
    item = Item(id=item_row.id, name=item_row.name, description=item_row.description)
    if settings.mock_mode:
        scoring, scoring_meta = _mock_scoring(fluency, flexibility, flex_codes, per_idea)
    else:
        scoring, scoring_meta = run_scoring(
            item, fluency, flexibility, flex_codes, per_idea, client or _client()
        )

    stable_sample = version.participant_count >= item_row.originality_min_participants
    row.scoring = scoring.model_dump()
    row.scoring_meta = {
        **scoring_meta,
        "frequency_source": "live" if uses_live else "codebook_snapshot",
        "eligible_participant_count": version.participant_count,
        "eligible_response_count": version.response_count,
    }
    row.fluency = scoring.fluency
    row.flexibility = scoring.flexibility
    row.originality = scoring.originality
    row.elaboration = scoring.elaboration
    row.codebook_version_id = version.id
    row.scoring_status = (
        ResponseScoringStatus.FINAL
        if stable_sample and not uses_live
        else ResponseScoringStatus.PROVISIONAL
    )
    row.scored_at = datetime.now(timezone.utc)


def backfill_item_scores(item_id: str) -> None:
    """Tự chấm bù các response đầu sau khi item vừa đạt ngưỡng hiệu chuẩn."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(ResponseModel)
            .where(
                ResponseModel.item_id == item_id,
                ResponseModel.scoring_status == ResponseScoringStatus.COLLECTING,
            )
            .order_by(ResponseModel.created_at)
        ).all()
        client = None if settings.mock_mode else _client()
        for row in rows:
            _score_row(db, row, client)
        db.commit()


def reprocess_item_scores_in_session(db: Session, item_id: str) -> int:
    """Chấm lại trong transaction hiện tại để thấy ngay quyết định vừa thay đổi."""
    item = db.get(ItemModel, item_id)
    if item is None or not item.active_codebook_version_id:
        return 0
    rows = db.scalars(
        select(ResponseModel).where(
            ResponseModel.item_id == item_id,
            ResponseModel.scoring_status != ResponseScoringStatus.PENDING_REVIEW,
            ResponseModel.scoring_status != ResponseScoringStatus.EXCLUDED,
        )
    ).all()
    client = None if settings.mock_mode else _client()
    for row in rows:
        _score_row(db, row, client)
    return len(rows)


def reprocess_item_scores(item_id: str) -> int:
    """Chấm lại mọi response đã map chắc chắn sau khi codebook bị điều chỉnh."""
    with SessionLocal() as db:
        processed = reprocess_item_scores_in_session(db, item_id)
        db.commit()
        return processed


def _reject_unreferenced_codes(db: Session, item_id: str) -> None:
    """Sau remap, code AI không còn ý VALID phải bị loại khỏi codebook hoạt động."""
    referenced_ids = set(
        db.scalars(
            select(ResponseIdea.code_id)
            .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
            .where(
                ResponseModel.item_id == item_id,
                ResponseIdea.mapping_status == "VALID",
                ResponseIdea.code_id.is_not(None),
            )
            .distinct()
        ).all()
    )
    for code in db.scalars(select(ItemCode).where(ItemCode.item_id == item_id)).all():
        if code.id not in referenced_ids and not code.admin_locked:
            code.validation_status = CodeValidationStatus.REJECTED
            code.rejection_reason = (
                "Code không còn ý hợp lệ tham chiếu sau khi admin phân loại lại."
            )


def reprocess_item_mappings(item_id: str) -> int:
    """Chạy lại Extraction + Curator cho toàn bộ response của một đồ vật."""
    with SessionLocal() as db:
        item_row = db.get(ItemModel, item_id)
        if item_row is None:
            return 0
        rows = db.scalars(
            select(ResponseModel)
            .where(ResponseModel.item_id == item_id)
            .order_by(ResponseModel.created_at)
        ).all()
        if not rows:
            return 0

        item = Item(id=item_row.id, name=item_row.name, description=item_row.description)
        client = None if settings.mock_mode else _client()
        for row in rows:
            existing_codes = list_curator_codes(db, item_id)
            if settings.mock_mode:
                extraction, curator = _mock_mapping(item, row.raw_input, existing_codes)
                extraction_meta = {"mock": True, "stage": "idea_extraction"}
                curator_meta = {"mock": True, "stage": "code_curator"}
            else:
                extraction, extraction_meta = run_idea_extraction(
                    item, row.raw_input, client
                )
                curator, curator_meta = run_code_curator(
                    item, extraction, existing_codes, client
                )
                if _needs_curator_retry(curator, extraction):
                    second_curator, second_meta = run_code_curator(
                        item, extraction, existing_codes, client
                    )
                    curator = _prefer_confident(curator, second_curator)
                    curator_meta = {
                        "runs": [curator_meta, second_meta],
                        "strategy": "prefer_confident",
                    }

            db.execute(delete(ResponseIdea).where(ResponseIdea.response_id == row.id))
            mapping, has_uncertain = persist_mapping(
                db,
                item=item_row,
                response=row,
                extraction=extraction,
                curator=curator,
            )
            row.mapping = mapping.model_dump()
            row.mapping_meta = {
                "idea_extraction": extraction_meta,
                "code_curator": curator_meta,
                "remapped_by": "ADMIN",
                "remapped_at": datetime.now(timezone.utc).isoformat(),
            }
            row.scoring = {}
            row.scoring_meta = {"invalidated_by": "ADMIN_FULL_REMAP"}
            row.fluency = 0
            row.flexibility = 0
            row.originality = 0
            row.elaboration = 0
            row.codebook_version_id = None
            row.scored_at = None
            row.scoring_status = (
                ResponseScoringStatus.PENDING_REVIEW
                if has_uncertain
                else ResponseScoringStatus.COLLECTING
            )

        _reject_unreferenced_codes(db, item_id)
        participant_count = eligible_participant_count(db, item_id)
        if item_row.active_codebook_version_id:
            mark_item_for_recalculation(db, item_id)
            version = create_codebook_version(db, item_row, participant_count)
        else:
            version, _ = maybe_refresh_codebook(db, item_row)

        if version:
            for row in rows:
                if row.scoring_status != ResponseScoringStatus.PENDING_REVIEW:
                    _score_row(db, row, client)
        db.commit()
        return len(rows)


def retry_pending_item_mappings(item_id: str, limit: int = 1) -> int:
    """Tự chạy lại một số mapping chưa chắc; giới hạn để kiểm soát chi phí LLM."""
    if settings.mock_mode:
        return 0
    version_changed = False
    resolved = 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(ResponseModel)
            .where(
                ResponseModel.item_id == item_id,
                ResponseModel.scoring_status == ResponseScoringStatus.PENDING_REVIEW,
            )
            .order_by(ResponseModel.created_at)
            .limit(limit)
        ).all()
        client = _client()
        for row in rows:
            retry_count = int(row.mapping_meta.get("pending_retry_count", 0))
            if retry_count >= 2:
                continue
            item_row = row.item
            item = Item(id=item_row.id, name=item_row.name, description=item_row.description)
            extraction, extraction_meta = run_idea_extraction(item, row.raw_input, client)
            curator, curator_meta = run_code_curator(
                item, extraction, list_curator_codes(db, item_id), client
            )
            db.execute(delete(ResponseIdea).where(ResponseIdea.response_id == row.id))
            mapping, has_uncertain = persist_mapping(
                db, item=item_row, response=row, extraction=extraction, curator=curator
            )
            row.mapping = mapping.model_dump()
            row.mapping_meta = {
                "idea_extraction": extraction_meta,
                "code_curator": curator_meta,
                "pending_retry_count": retry_count + 1,
            }
            if not has_uncertain:
                row.scoring_status = ResponseScoringStatus.COLLECTING
                version, changed = maybe_refresh_codebook(db, item_row)
                version_changed = version_changed or changed
                if version:
                    _score_row(db, row, client)
                resolved += 1
        db.commit()
    if version_changed:
        reprocess_item_scores(item_id)
    return resolved


def _status_message(status: ResponseScoringStatus) -> str:
    return {
        ResponseScoringStatus.COLLECTING: (
            "Câu trả lời đã được lưu và đang đóng góp vào dữ liệu hiệu chuẩn. "
            "Hệ thống sẽ tự chấm bù khi đủ mẫu."
        ),
        ResponseScoringStatus.PENDING_REVIEW: (
            "Một số ý cần AI đối chiếu lại. Dữ liệu đã được giữ nguyên và chưa bị tính là 0."
        ),
        ResponseScoringStatus.PROVISIONAL: (
            "Đây là điểm tạm thời; hệ thống sẽ tự cập nhật khi mẫu chuẩn lớn hơn."
        ),
        ResponseScoringStatus.FINAL: "Điểm được tính theo phiên bản codebook đã đóng.",
        ResponseScoringStatus.EXCLUDED: "Lượt này không được đưa vào mẫu chuẩn.",
    }[status]


def _to_response(row: ResponseModel) -> ScoreResponse:
    return ScoreResponse(
        response_id=row.id,
        item=Item(id=row.item.id, name=row.item.name, description=row.item.description),
        raw_input=row.raw_input,
        mapping=MappingResult.model_validate(row.mapping),
        scoring=ScoringResult.model_validate(row.scoring) if row.scoring else None,
        scoring_status=row.scoring_status.value,
        codebook_version_id=row.codebook_version_id,
        status_message=_status_message(row.scoring_status),
    )


def create_response(
    db: Session,
    req: ScoreRequest,
    participant: ParticipantModel,
    background_tasks: BackgroundTasks | None = None,
) -> ScoreResponse:
    item_row = db.get(ItemModel, req.item_id)
    if item_row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    raw = req.raw_input.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Câu trả lời rỗng.")

    item = Item(id=item_row.id, name=item_row.name, description=item_row.description)
    row = ResponseModel(
        id=str(uuid.uuid4()),
        participant_id=participant.id,
        item_id=item_row.id,
        raw_input=raw,
        mapping={},
        scoring={},
        # Mỗi lần submit là một quan sát của mẫu chuẩn, kể cả cùng người làm lại cùng đồ vật.
        calibration_eligible=True,
        scoring_status=ResponseScoringStatus.COLLECTING,
    )
    db.add(row)
    db.flush()

    existing_codes = list_curator_codes(db, item_row.id)
    if settings.mock_mode:
        extraction, curator = _mock_mapping(item, raw, existing_codes)
        mapping_meta = {"mock": True, "stage": "idea_extraction"}
        curator_meta = {"mock": True, "stage": "code_curator"}
        client = None
    else:
        client = _client()
        extraction, mapping_meta = run_idea_extraction(item, raw, client) #trích xuất ý tưởng
        curator, curator_meta = run_code_curator(item, extraction, existing_codes, client)
        if _needs_curator_retry(curator, extraction):
            second_curator, second_meta = run_code_curator(
                item, extraction, existing_codes, client
            )
            curator = _prefer_confident(curator, second_curator)
            curator_meta = {"runs": [curator_meta, second_meta], "strategy": "prefer_confident"}

    mapping, has_uncertain = persist_mapping(
        db, item=item_row, response=row, extraction=extraction, curator=curator
    )
    row.mapping = mapping.model_dump()
    row.mapping_meta = {"idea_extraction": mapping_meta, "code_curator": curator_meta}
    if has_uncertain:
        row.scoring_status = ResponseScoringStatus.PENDING_REVIEW

    version, version_changed = maybe_refresh_codebook(db, item_row)
    if version and not has_uncertain:
        _score_row(db, row, client)

    db.commit()
    db.refresh(row)
    if version_changed and background_tasks is not None:
        # Bao gồm cả chấm bù lần kích hoạt và tính lại điểm provisional khi refresh.
        background_tasks.add_task(reprocess_item_scores, item_row.id)
    if background_tasks is not None:
        background_tasks.add_task(retry_pending_item_mappings, item_row.id)
    return _to_response(row)


def get_response_detail(db: Session, response_id: str) -> ScoreResponse:
    row = db.get(ResponseModel, response_id)
    if row is None:
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
        )
        for row in rows
    ]
