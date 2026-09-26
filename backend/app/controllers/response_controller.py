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
    CodeValidationStatus,
    Item as ItemModel,
    ItemCode,
    Participant as ParticipantModel,
    Response as ResponseModel,
    ResponseIdea,
    ResponseScoringStatus,
)
from app.pipeline.codebook_service import (
    item_is_ready_for_scoring,
    list_curator_codes,
    originality_for_response,
    persist_mapping,
    refresh_final_frequency_scores,
    refresh_item_scoring_state,
)
from app.pipeline.dynamic_mapping import (
    normalize_code_name,
    run_code_curator,
    run_idea_extraction,
)
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
    FunctionalSignature,
)


def _client() -> OpenAI:
    """Khởi tạo client OpenAI-compatible theo provider được chọn trong môi trường."""
    if not settings.active_llm_api_key:
        env_name = {
            "groq": "GROQ_API_KEY",
            "cloudflare": "CLOUDFLARE_API_TOKEN",
            "byteplus": "BYTEPLUS_API_KEY",
        }[settings.llm_provider]
        raise HTTPException(status_code=500, detail=f"{env_name} chưa được cấu hình.")
    if settings.llm_provider == "cloudflare" and not settings.cloudflare_account_id:
        raise HTTPException(
            status_code=500,
            detail="CLOUDFLARE_ACCOUNT_ID chưa được cấu hình.",
        )
    return OpenAI(
        base_url=settings.active_llm_base_url.rstrip("/"),
        api_key=settings.active_llm_api_key,
        # Tự quản lý retry trong chat_json để tôn trọng Retry-After và tránh retry lồng nhau.
        max_retries=0,
    )


def _embedding_client() -> OpenAI | None:
    """Tạo client Cloudflare riêng cho embedding; local chỉ dùng khi cấu hình rõ."""
    if settings.embedding_provider == "local":
        return None
    if not settings.cloudflare_api_token or not settings.cloudflare_account_id:
        raise HTTPException(
            status_code=500,
            detail=(
                "Semantic embedding cần CLOUDFLARE_API_TOKEN và "
                "CLOUDFLARE_ACCOUNT_ID."
            ),
        )
    return OpenAI(
        base_url=(
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{settings.cloudflare_account_id}/ai/v1"
        ),
        api_key=settings.cloudflare_api_token,
        max_retries=0,
        timeout=settings.embedding_timeout_seconds,
    )


def _mock_mapping(
    item: Item, raw: str, existing_codes: list[dict]
) -> tuple[IdeaExtractionResult, CuratorResult]:
    """Mock có cùng contract hai tầng để test không vô tình quay lại code tĩnh."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()][:10]
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                original=line,
                normalized=line,
                status="VALID",
                uses_target_object=True,
                object_used=item.name,
                target_object_role="Đóng vai trò vật thể chính trong công dụng mô phỏng.",
                line_index=index,
                functional_signature=FunctionalSignature(
                    goal=line,
                    object_role=f"Dùng {item.name} làm vật thể chính",
                    mechanism="Cơ chế mô phỏng ổn định",
                ),
            )
            for index, line in enumerate(lines)
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
                    code_relation="SAME_CATEGORY",
                    target_object_confirmed=True,
                    target_object_role="Dùng đúng đồ vật mục tiêu.",
                    functional_signature=extraction.ideas[index].functional_signature,
                    existing_code_evaluations=[
                        {
                            "code_id": existing["id"],
                            "relation": "SAME_CATEGORY",
                            "goal_match": True,
                            "role_match": True,
                            "mechanism_match": True,
                            "excluded_by": "",
                            "verdict": "MATCH",
                        }
                    ],
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
                    functional_signature=extraction.ideas[index].functional_signature,
                    inclusion_rules=[f"Dùng {item.name} theo chức năng {line[:80]}"],
                    exclusion_rules=["Không bao gồm mục đích hoặc cơ chế khác"],
                    positive_examples=[line],
                    policy_gates={
                        "response_is_valid": True,
                        "no_existing_code_covers": True,
                        "functionally_distinct": True,
                        "granularity_consistent": True,
                        "paraphrase_stable": True,
                        "counterexample_passed": True,
                    },
                    reviewed_by_challenger=True,
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
            summary_vi="[MOCK] Điểm được tính từ dữ liệu tại thời điểm nộp bài.",
        ),
        {"mock": True},
    )


def _needs_curator_retry(curator: CuratorResult, extraction: IdeaExtractionResult) -> bool:
    expected = sum(
        idea.status == "VALID" and idea.uses_target_object for idea in extraction.ideas
    )
    return len(curator.decisions) < expected or any(
        decision.decision in {"OUT_OF_CODEBOOK", "UNCERTAIN"}
        or (
            decision.decision != "INVALID"
            and (not decision.target_object_confirmed or not decision.target_object_role.strip())
        )
        for decision in curator.decisions
    )


def _prefer_confident(first: CuratorResult, second: CuratorResult) -> CuratorResult:
    """Ưu tiên quyết định đã qua policy; confidence chỉ dùng phá thế hoà để kiểm toán."""
    rank = {
        "CREATE_NEW": 4,
        "EXPAND_EXISTING": 4,
        "MATCH_EXISTING": 4,
        "INVALID": 3,
        "UNCERTAIN": 1,
        "OUT_OF_CODEBOOK": 0,
    }
    selected = {decision.idea_index: decision for decision in first.decisions}
    for decision in second.decisions:
        previous = selected.get(decision.idea_index)
        if (
            previous is not None
            and rank[previous.decision] == 4
            and rank[decision.decision] == 4
        ):
            previous_target = (
                normalize_code_name(previous.code_name or "")
                if previous.decision == "CREATE_NEW"
                else previous.existing_code_id or ""
            )
            current_target = (
                normalize_code_name(decision.code_name or "")
                if decision.decision == "CREATE_NEW"
                else decision.existing_code_id or ""
            )
            if previous.decision != decision.decision or previous_target != current_target:
                selected[decision.idea_index] = previous.model_copy(
                    update={
                        "decision": "UNCERTAIN",
                        "code_relation": "UNCERTAIN",
                        "existing_code_id": None,
                        "reason": (
                            "Hai lượt Curator đưa ra quyết định đã qua policy nhưng không cùng "
                            "category; backend không chọn theo confidence."
                        ),
                    }
                )
                continue
        if previous is None or (rank[decision.decision], decision.confidence) > (
            rank[previous.decision],
            previous.confidence,
        ):
            selected[decision.idea_index] = decision
    return CuratorResult(decisions=list(selected.values()))


def _score_row(
    db: Session,
    row: ResponseModel,
    client: OpenAI | None = None,
) -> bool:
    """Chấm đúng một lần cho response đã phân loại xong khi item đủ ngưỡng."""
    item_row = row.item
    if (
        row.scoring_status in {ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED}
        or not item_is_ready_for_scoring(db, item_row)
        or row.scoring_status == ResponseScoringStatus.FINAL
    ):
        return False

    fluency, flexibility, flex_codes, per_idea, frequency_basis = originality_for_response(db, row)
    item = Item(id=item_row.id, name=item_row.name, description=item_row.description)
    if settings.mock_mode:
        scoring, scoring_meta = _mock_scoring(fluency, flexibility, flex_codes, per_idea)
    else:
        scoring, scoring_meta = run_scoring(
            item, fluency, flexibility, flex_codes, per_idea, client or _client()
        )

    scored_at = datetime.now(timezone.utc)
    history = list((row.scoring_meta or {}).get("history", []))
    row.scoring = scoring.model_dump()
    row.scoring_meta = {
        **scoring_meta,
        "calculated_at": scored_at.isoformat(),
        "frequency_basis": frequency_basis,
        "history": history,
    }
    row.fluency = scoring.fluency
    row.flexibility = scoring.flexibility
    row.originality = scoring.originality
    row.elaboration = scoring.elaboration
    row.scoring_status = ResponseScoringStatus.FINAL
    row.scored_at = scored_at
    return True


def backfill_item_scores(item_id: str) -> None:
    """Chấm một lần cho các response đang chờ khi đồ vật vừa đủ cả hai ngưỡng."""
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
    """Chấm bù các response COLLECTING khi item vừa đủ ngưỡng."""
    item = db.get(ItemModel, item_id)
    if item is None or not item_is_ready_for_scoring(db, item):
        return 0
    query = select(ResponseModel).where(
        ResponseModel.item_id == item_id,
        ResponseModel.scoring_status == ResponseScoringStatus.COLLECTING,
    )
    rows = db.scalars(query.order_by(ResponseModel.created_at)).all()
    client = None if settings.mock_mode else _client()
    processed = 0
    for row in rows:
        processed += int(_score_row(db, row, client))
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
        embedding_client = None if settings.mock_mode else _embedding_client()
        for row in rows:
            existing_codes = list_curator_codes(db, item_id)
            if settings.mock_mode:
                extraction, curator = _mock_mapping(item, row.raw_input, existing_codes)
                extraction_meta = {"mock": True, "stage": "idea_extraction"}
                curator_meta = {"mock": True, "stage": "code_curator"}
            else:
                extraction, extraction_meta = run_idea_extraction(
                    item, row.raw_input, client, embedding_client
                )
                curator, curator_meta = run_code_curator(
                    item, extraction, existing_codes, client, embedding_client
                )
                if _needs_curator_retry(curator, extraction):
                    second_curator, second_meta = run_code_curator(
                        item, extraction, existing_codes, client, embedding_client
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
            score_history = list((row.scoring_meta or {}).get("history", []))
            if row.scoring:
                score_history.append(
                    {
                        "scoring": row.scoring,
                        "scoring_meta": {
                            key: value
                            for key, value in (row.scoring_meta or {}).items()
                            if key != "history"
                        },
                        "replaced_at": datetime.now(timezone.utc).isoformat(),
                        "reason": "ADMIN_FULL_REMAP",
                    }
                )
            row.scoring = {}
            row.scoring_meta = {
                "invalidated_by": "ADMIN_FULL_REMAP",
                "history": score_history,
            }
            row.fluency = 0
            row.flexibility = 0
            row.originality = 0
            row.elaboration = 0
            row.scored_at = None
            row.scoring_status = (
                ResponseScoringStatus.PENDING_REVIEW
                if has_uncertain
                else ResponseScoringStatus.COLLECTING
            )

        _reject_unreferenced_codes(db, item_id)
        refresh_item_scoring_state(db, item_row)
        if item_is_ready_for_scoring(db, item_row):
            for row in rows:
                if row.scoring_status != ResponseScoringStatus.PENDING_REVIEW:
                    _score_row(db, row, client)
        db.commit()
        return len(rows)


def retry_pending_item_mappings(item_id: str, limit: int = 1) -> int:
    """Tự chạy lại một số mapping chưa chắc; giới hạn để kiểm soát chi phí LLM."""
    if settings.mock_mode:
        return 0
    became_ready = False
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
        embedding_client = _embedding_client()
        for row in rows:
            retry_count = int(row.mapping_meta.get("pending_retry_count", 0))
            if retry_count >= 2:
                continue
            item_row = row.item
            item = Item(id=item_row.id, name=item_row.name, description=item_row.description)
            extraction, extraction_meta = run_idea_extraction(
                item, row.raw_input, client, embedding_client
            )
            curator, curator_meta = run_code_curator(
                item,
                extraction,
                list_curator_codes(db, item_id),
                client,
                embedding_client,
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
                changed = refresh_item_scoring_state(db, item_row)
                became_ready = became_ready or changed
                if item_is_ready_for_scoring(db, item_row):
                    db.flush()
                    refresh_final_frequency_scores(db, item_id)
                    _score_row(db, row, client)
                resolved += 1
        if became_ready:
            reprocess_item_scores_in_session(db, item_id)
        db.commit()
    return resolved


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
        ResponseScoringStatus.FINAL: "Điểm đã được chốt sau khi đồ vật đạt ngưỡng dữ liệu nghiên cứu.",
        ResponseScoringStatus.EXCLUDED: "Lượt này bị loại khỏi dữ liệu theo quyết định quản trị.",
    }[status]


def _to_response(row: ResponseModel) -> ScoreResponse:
    return ScoreResponse(
        response_id=row.id,
        item=Item(id=row.item.id, name=row.item.name, description=row.item.description),
        raw_input=row.raw_input,
        mapping=MappingResult.model_validate(row.mapping),
        scoring=ScoringResult.model_validate(row.scoring) if row.scoring else None,
        scoring_status=row.scoring_status.value,
        status_message=_status_message(row.scoring_status),
    )


def create_response(
    db: Session,
    req: ScoreRequest,
    participant: ParticipantModel,
    background_tasks: BackgroundTasks | None = None,
) -> ScoreResponse:
    # Khóa theo đồ vật trong suốt chu trình mã hóa để hai lượt gửi đồng thời
    # không thể cùng tạo hai code cho một chức năng mới.
    item_row = db.scalar(
        select(ItemModel)
        .where(ItemModel.id == req.item_id)
        .with_for_update()
    )
    if item_row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    raw = "\n".join(req.responses).strip()
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
        embedding_client = _embedding_client()
        extraction, mapping_meta = run_idea_extraction(
            item, req.responses, client, embedding_client
        )
        curator, curator_meta = run_code_curator(
            item, extraction, existing_codes, client, embedding_client
        )
        if _needs_curator_retry(curator, extraction):
            second_curator, second_meta = run_code_curator(
                item, extraction, existing_codes, client, embedding_client
            )
            curator = _prefer_confident(curator, second_curator)
            curator_meta = {"runs": [curator_meta, second_meta], "strategy": "prefer_confident"}

    mapping, has_uncertain = persist_mapping(
        db, item=item_row, response=row, extraction=extraction, curator=curator
    )
    row.mapping = mapping.model_dump()
    row.mapping_meta = {
        "idea_extraction": mapping_meta,
        "code_curator": curator_meta,
    }
    row.scoring_status = (
        ResponseScoringStatus.PENDING_REVIEW
        if has_uncertain
        else ResponseScoringStatus.COLLECTING
    )
    became_ready = refresh_item_scoring_state(db, item_row)
    if item_is_ready_for_scoring(db, item_row):
        db.flush()
        refresh_final_frequency_scores(db, item_row.id)
        if became_ready:
            reprocess_item_scores_in_session(db, item_row.id)
        else:
            _score_row(db, row, client)

    retry_previous_pending = bool(
        db.scalar(
            select(ResponseModel.id).where(
                ResponseModel.item_id == item_row.id,
                ResponseModel.id != row.id,
                ResponseModel.scoring_status == ResponseScoringStatus.PENDING_REVIEW,
            ).limit(1)
        )
    )
    db.commit()
    db.refresh(row)
    if background_tasks is not None and retry_previous_pending and not settings.mock_mode:
        background_tasks.add_task(retry_pending_item_mappings, item_row.id, 1)
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
        )
        for row in rows
    ]
