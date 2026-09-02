"""Nghiệp vụ nộp bài, xem kết quả, xem lịch sử — có kiểm tra quyền sở hữu."""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from google import genai
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Item as ItemModel
from app.models.models import Response as ResponseModel
from app.models.models import User as UserModel
from app.pipeline.mapping import run_mapping
from app.pipeline.scoring import run_scoring
from app.pipeline.compute_scores import compute_response_scores
from app.pipeline.code_stats_db import DBCodeStatsStore
from app.schemas.schemas import (
    Item,
    MappedIdea,
    MappingResult,
    PerIdeaScore,
    ResponseSummary,
    ScoreRequest,
    ScoreResponse,
    ScoringResult,
)


def _client() -> genai.Client:
    if not settings.google_api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY chưa được cấu hình.")
    return genai.Client(api_key=settings.google_api_key)


def _mock_score(item: Item, raw: str) -> tuple:
    lines = [l.strip() for l in raw.replace(",", "\n").splitlines() if l.strip()]
    ideas = []
    for i, line in enumerate(lines[:12]):
        ideas.append(
            MappedIdea(
                original=line,
                normalized=line,
                code=item.codes[i % len(item.codes)] if item.codes else "Khác",
                status="VALID",
                reason="",
            )
        )
    unique_codes = list(dict.fromkeys(i.code for i in ideas if i.status == "VALID"))
    per = [PerIdeaScore(normalized=i.normalized, code=i.code, originality=1, elaboration=2) for i in ideas]
    mapping = MappingResult(ideas=ideas)
    scoring = ScoringResult(
        fluency=len(ideas),
        flexibility=len(unique_codes),
        flexibility_codes=unique_codes,
        originality=len(ideas),
        elaboration=len(ideas) * 2,
        per_idea_scores=per,
        summary_vi="[MOCK] Đây là kết quả thử nghiệm — chưa kết nối Gemini.",
    )
    return mapping, {}, scoring, {}


def create_response(db: Session, req: ScoreRequest, current_user: UserModel) -> ScoreResponse:
    item_row = db.get(ItemModel, req.item_id)
    if item_row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    raw = req.raw_input.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Câu trả lời rỗng.")

    item = Item(id=item_row.id, name=item_row.name, description=item_row.description, codes=item_row.codes)

    if settings.mock_mode:
        mapping, mapping_meta, scoring, scoring_meta = _mock_score(item, raw)
    else:
        client = _client()
        mapping, mapping_meta = run_mapping(item, raw, client)

        # Fluency/Flexibility/Originality: công thức, dùng DBCodeStatsStore
        # (cộng dồn ngay response này vào bảng tần suất tích lũy của item).
        stats_store = DBCodeStatsStore(db)
        fluency, flexibility, flex_codes, per_idea_orig, sufficient_data = (
            compute_response_scores(item.id, mapping, stats_store)
        )

        # Elaboration: LLM, nhận điểm Originality đã tính sẵn để ghép lại.
        scoring, scoring_meta = run_scoring(
            item, fluency, flexibility, flex_codes, per_idea_orig, client
        )
        scoring_meta["originality_sufficient_data"] = sufficient_data

    response_id = str(uuid.uuid4())
    row = ResponseModel(
        id=response_id,
        user_id=current_user.id,  # <-- gắn với người đang đăng nhập, khác bản trước (None)
        item_id=item.id,
        raw_input=raw,
        mapping=mapping.model_dump(),
        scoring=scoring.model_dump(),
        mapping_meta=mapping_meta,
        scoring_meta=scoring_meta,
        fluency=scoring.fluency,
        flexibility=scoring.flexibility,
        originality=scoring.originality,
        elaboration=scoring.elaboration,
    )
    db.add(row)
    db.commit()

    return ScoreResponse(
        response_id=response_id,
        item=item,
        raw_input=raw,
        mapping=mapping,
        scoring=scoring,
    )


def get_response_detail(db: Session, response_id: str, current_user: UserModel) -> ScoreResponse:
    row = db.get(ResponseModel, response_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả.")

    # User thường chỉ xem được response của chính mình; admin xem được tất cả.
    if current_user.role != "admin" and row.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền xem kết quả này."
        )

    return ScoreResponse(
        response_id=row.id,
        item=Item(
            id=row.item.id,
            name=row.item.name,
            description=row.item.description,
            codes=row.item.codes,
        ),
        raw_input=row.raw_input,
        mapping=row.mapping,
        scoring=row.scoring,
    )


def list_responses_for_user(db: Session, current_user: UserModel) -> list[ResponseSummary]:
    """Admin -> thấy TẤT CẢ response của mọi người.
    User thường -> chỉ thấy response của chính mình.
    """
    stmt = select(ResponseModel).order_by(ResponseModel.created_at.desc())
    if current_user.role != "admin":
        stmt = stmt.where(ResponseModel.user_id == current_user.id)
    rows = db.scalars(stmt).all()
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
        )
        for row in rows
    ]