"""Nghiệp vụ thống kê dành riêng cho quản trị viên."""

import csv
import io
import uuid

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, distinct, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Item as ItemModel
from app.models.models import (
    CodeMaturityStatus,
    CodeValidationStatus,
    ItemCode,
    ItemCalibrationStatus,
    ResponseIdea,
    ResponseScoringStatus,
    User as UserModel,
)
from app.pipeline.centroid import rebuild_confirmed_members
from app.pipeline.code_retrieval import core_signature_text, functional_key
from app.pipeline.embedding import embedding_model as active_embedding_model
from app.pipeline.embedding import local_embedding
from app.pipeline.codebook_service import (
    item_is_ready_for_scoring,
    list_curator_codes,
    refresh_item_scoring_state,
    refresh_final_frequency_scores,
    qualifying_idea_count,
    qualifying_participant_count,
    qualifying_response_count,
)
from app.pipeline.cluster_proposals import propose_clusters
from app.pipeline.dynamic_mapping import normalize_code_name
from app.controllers.response_controller import (
    _to_response,
    reprocess_item_mappings,
    reprocess_item_scores_in_session,
)
from app.models.models import Participant as ParticipantModel
from app.models.models import Response as ResponseModel


def pipeline_audits(db: Session, item_id: str, limit: int) -> list[dict]:
    """Nhật ký resolver/audit tự động để quản trị quan sát, không phê duyệt mã."""
    from app.models.models import PipelineAudit
    return [{"id": row.id, "event": row.event, "response_id": row.response_id,
             "created_at": row.created_at.isoformat(), "payload": row.payload}
            for row in db.scalars(select(PipelineAudit).where(PipelineAudit.item_id == item_id)
                                 .order_by(PipelineAudit.created_at.desc()).limit(limit)).all()]
from app.schemas.schemas import (
    AdminClusterAudit,
    AdminDailyStat,
    AdminAiGroupStats,
    AdminDashboardStats,
    AdminItemBreakdown,
    AdminCodePatch,
    AdminCodebookCode,
    AdminCodebookOverview,
    AdminCodebookSummary,
    AdminCodeOption,
    AdminCuratorAudit,
    AdminCuratorDecisionIdea,
    AdminExtractionAudit,
    AdminExtractionExcludedIdea,
    AdminParticipantDetail,
    AdminParticipantSummary,
    AdminRecentResponse,
    AdminMappingReviewIdea,
    AdminMappingReviewList,
    AdminMappingReviewResolution,
    AdminMappingReviewResult,
    AdminScoringStatusCounts,
    MappedIdea,
    MappingResult,
    ParticipantOut,
    ResponseSummary,
    ScoreResponse,
)


def get_cluster_audit(db: Session, item_id: str, *, limit: int = 200) -> AdminClusterAudit:
    """Gom ý chưa có mã trên dữ liệu đã lưu; không thay mapping/codebook/điểm."""
    if db.get(ItemModel, item_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    criteria = (
        ResponseModel.item_id == item_id,
        ResponseModel.processing_state == "DONE",
        ResponseModel.scoring_status == ResponseScoringStatus.PENDING_REVIEW,
        ResponseIdea.mapping_status == "VALID",
        ResponseIdea.code_id.is_(None),
        ResponseIdea.review_status == "PENDING",
    )
    total = int(db.scalar(
        select(func.count(ResponseIdea.id))
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .where(*criteria)
    ) or 0)
    rows = db.scalars(
        select(ResponseIdea)
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .where(*criteria)
        .order_by(ResponseIdea.created_at.desc(), ResponseIdea.id.desc())
        .limit(limit)
    ).all()
    ideas = [{
        "idea_id": row.id,
        "response_id": row.response_id,
        "original": row.original,
        "normalized": row.normalized,
        "functional_signature": row.functional_signature or {},
        "embedding": row.embedding or [],
        "embedding_model": row.embedding_model or "",
    } for row in rows]
    report = propose_clusters(
        ideas, list_curator_codes(db, item_id),
        similarity_floor=settings.cluster_proposal_similarity_floor,
    )
    return AdminClusterAudit(
        item_id=item_id,
        total_pending_ideas=total,
        sampled_ideas=len(rows),
        truncated=total > len(rows),
        similarity_floor=settings.cluster_proposal_similarity_floor,
        **report,
    )


def get_response_detail(db: Session, response_id: str) -> ScoreResponse:
    """Admin xem bài qua route riêng, không mượn định danh participant."""
    row = db.get(ResponseModel, response_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài khảo sát.")
    return _to_response(row)


def retry_failed_response(db: Session, response_id: str) -> dict[str, str]:
    """Cho phép quản trị vận hành thử lại job đã hết số lần tự động."""
    row = db.scalar(select(ResponseModel).where(ResponseModel.id == response_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài khảo sát.")
    if row.processing_state != "FAILED":
        raise HTTPException(status_code=409, detail="Bài này không ở trạng thái xử lý thất bại.")
    row.processing_state = "DONE" if (row.mapping or {}).get("ideas") else "QUEUED"
    row.processing_attempts = 0
    row.processing_claim_token = None
    row.processing_lease_until = None
    row.processing_error = ""
    db.commit()
    return {"response_id": row.id, "processing_state": row.processing_state}


def _to_summary(row: ResponseModel) -> ResponseSummary:
    return ResponseSummary(
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


def _to_recent(row: ResponseModel) -> AdminRecentResponse:
    return AdminRecentResponse(
        response_id=row.id,
        created_at=row.created_at.isoformat() if row.created_at else "",
        participant_id=row.participant_id,
        item_id=row.item_id,
        item_name=row.item.name if row.item else "",
        fluency=row.fluency,
        flexibility=row.flexibility,
        originality=row.originality,
        elaboration=row.elaboration,
        scoring_status=row.scoring_status.value,
    )


def _ai_group_stats(db: Session) -> list[AdminAiGroupStats]:
    """Tổng hợp theo người để một người nộp nhiều lượt không lấn át trung bình nhóm."""
    groups = ("LOW", "HIGH")
    participant_counts = dict(
        db.execute(
            select(ParticipantModel.ai_usage_group, func.count(ParticipantModel.id))
            .where(ParticipantModel.ai_usage_group.in_(groups))
            .group_by(ParticipantModel.ai_usage_group)
        ).all()
    )
    response_counts = dict(
        db.execute(
            select(ParticipantModel.ai_usage_group, func.count(ResponseModel.id))
            .join(ResponseModel, ResponseModel.participant_id == ParticipantModel.id)
            .where(ParticipantModel.ai_usage_group.in_(groups))
            .group_by(ParticipantModel.ai_usage_group)
        ).all()
    )
    final_counts = dict(
        db.execute(
            select(ParticipantModel.ai_usage_group, func.count(ResponseModel.id))
            .join(ResponseModel, ResponseModel.participant_id == ParticipantModel.id)
            .where(
                ParticipantModel.ai_usage_group.in_(groups),
                ResponseModel.scoring_status == ResponseScoringStatus.FINAL,
            )
            .group_by(ParticipantModel.ai_usage_group)
        ).all()
    )
    participant_means = (
        select(
            ParticipantModel.ai_usage_group.label("group_name"),
            ResponseModel.participant_id.label("participant_id"),
            func.avg(ResponseModel.fluency).label("fluency"),
            func.avg(ResponseModel.flexibility).label("flexibility"),
            func.avg(ResponseModel.originality).label("originality"),
            func.avg(ResponseModel.elaboration).label("elaboration"),
        )
        .join(ResponseModel, ResponseModel.participant_id == ParticipantModel.id)
        .where(
            ParticipantModel.ai_usage_group.in_(groups),
            ResponseModel.scoring_status == ResponseScoringStatus.FINAL,
        )
        .group_by(ParticipantModel.ai_usage_group, ResponseModel.participant_id)
        .subquery()
    )
    score_rows = db.execute(
        select(
            participant_means.c.group_name,
            func.avg(participant_means.c.fluency),
            func.avg(participant_means.c.flexibility),
            func.avg(participant_means.c.originality),
            func.avg(participant_means.c.elaboration),
        ).group_by(participant_means.c.group_name)
    ).all()
    scores = {row[0]: row[1:] for row in score_rows}
    return [
        AdminAiGroupStats(
            group=group,
            participant_count=int(participant_counts.get(group, 0)),
            response_count=int(response_counts.get(group, 0)),
            final_response_count=int(final_counts.get(group, 0)),
            mean_fluency=float(scores[group][0]) if group in scores else None,
            mean_flexibility=float(scores[group][1]) if group in scores else None,
            mean_originality=float(scores[group][2]) if group in scores else None,
            mean_elaboration=float(scores[group][3]) if group in scores else None,
        )
        for group in groups
    ]


def export_response_scores_csv(db: Session) -> str:
    """Xuất bảng rộng theo lượt để phân tích hai nhóm bằng R, SPSS hoặc Excel."""
    from app.controllers.analysis_export import prepare_export
    from app.pipeline.codebook_service import _eligible_query
    items = prepare_export(db)
    eligible_ids = {key for item in items for key in db.scalars(_eligible_query(item.id, ResponseModel.id)).all()}
    exported_at = datetime.now(timezone.utc).isoformat()
    rows = db.execute(
        select(ResponseModel, ParticipantModel, ItemModel)
        .join(ParticipantModel, ResponseModel.participant_id == ParticipantModel.id)
        .join(ItemModel, ResponseModel.item_id == ItemModel.id)
        .order_by(ResponseModel.created_at, ResponseModel.id)
    ).all()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "participant_id",
            "ai_usage_group",
            "age",
            "gender",
            "occupation",
            "response_id",
            "item_id",
            "item_name",
            "submitted_at",
            "scoring_status",
            "fluency",
            "flexibility",
            "originality",
            "elaboration",
            "data_source", "eligible", "attempt_for_item", "exported_at",
        ]
    )
    attempts = {}
    for response, participant, item in rows:
        eligible = response.id in eligible_ids
        has_final_score = response.scoring_status == ResponseScoringStatus.FINAL and eligible
        key = (participant.id, item.id)
        attempts[key] = attempts.get(key, 0) + 1
        writer.writerow(
            [
                participant.id,
                participant.ai_usage_group or "",
                participant.age if participant.age is not None else "",
                participant.gender or "",
                participant.occupation or "",
                response.id,
                item.id,
                item.name,
                response.created_at.isoformat() if response.created_at else "",
                response.scoring_status.value,
                response.fluency if has_final_score else "",
                response.flexibility if has_final_score else "",
                response.originality if has_final_score else "",
                response.elaboration if has_final_score else "",
                response.data_source, eligible, attempts[key], exported_at,
            ]
        )
    db.commit()
    return buffer.getvalue()


def get_dashboard_stats(db: Session) -> AdminDashboardStats:
    """Tổng hợp tiến độ thu thập dữ liệu và trạng thái chấm một lần."""
    total_participants = db.scalar(select(func.count()).select_from(ParticipantModel)) or 0
    total_responses = db.scalar(select(func.count()).select_from(ResponseModel)) or 0
    total_qualifying_responses = db.scalar(
        select(func.count()).select_from(ResponseModel).where(
            ResponseModel.scoring_status.notin_(
                [ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED]
            )
        )
    ) or 0
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    responses_last_7_days = db.scalar(
        select(func.count()).select_from(ResponseModel).where(ResponseModel.created_at >= week_ago)
    ) or 0
    responses_previous_7_days = db.scalar(
        select(func.count()).select_from(ResponseModel).where(
            ResponseModel.created_at >= two_weeks_ago,
            ResponseModel.created_at < week_ago,
        )
    ) or 0

    fourteen_days_ago = now - timedelta(days=13)
    raw_rows = db.scalars(
        select(ResponseModel).where(ResponseModel.created_at >= fourteen_days_ago)
    ).all()
    buckets: dict[str, int] = {}
    for row in raw_rows:
        key = row.created_at.date().isoformat()
        buckets[key] = buckets.get(key, 0) + 1

    daily_stats = []
    today = now.date()
    for offset in range(13, -1, -1):
        key = (today - timedelta(days=offset)).isoformat()
        daily_stats.append(AdminDailyStat(date=key, count=buckets.get(key, 0)))

    code_status_rows = db.execute(
        select(ItemCode.validation_status, func.count(ItemCode.id)).group_by(
            ItemCode.validation_status
        )
    ).all()
    code_status_counts = {status: count for status, count in code_status_rows}
    accepted_code_count = code_status_counts.get(CodeValidationStatus.ACCEPTED, 0)
    uncertain_code_count = code_status_counts.get(CodeValidationStatus.UNCERTAIN, 0)
    rejected_code_count = code_status_counts.get(CodeValidationStatus.REJECTED, 0)

    scoring_rows = db.execute(
        select(ResponseModel.scoring_status, func.count(ResponseModel.id)).group_by(
            ResponseModel.scoring_status
        )
    ).all()
    scoring_counts = {status: count for status, count in scoring_rows}

    by_item = []
    items = db.scalars(select(ItemModel).order_by(ItemModel.name)).all()
    for item in items:
        response_count = db.scalar(
            select(func.count()).select_from(ResponseModel).where(
                ResponseModel.item_id == item.id
            )
        ) or 0
        item_code_rows = db.execute(
            select(ItemCode.validation_status, func.count(ItemCode.id))
            .where(ItemCode.item_id == item.id)
            .group_by(ItemCode.validation_status)
        ).all()
        item_code_counts = {status: count for status, count in item_code_rows}
        by_item.append(
            AdminItemBreakdown(
                item_id=item.id,
                item_name=item.name,
                response_count=response_count,
                calibration_status=item.calibration_status.value,
                qualifying_response_count=qualifying_response_count(db, item.id),
                qualifying_idea_count=qualifying_idea_count(db, item.id),
                qualifying_participant_count=qualifying_participant_count(db, item.id),
                scoring_min_participants=item.scoring_min_participants,
                scoring_min_ideas=item.scoring_min_ideas,
                accepted_code_count=item_code_counts.get(CodeValidationStatus.ACCEPTED, 0),
                uncertain_code_count=item_code_counts.get(CodeValidationStatus.UNCERTAIN, 0),
                rejected_code_count=item_code_counts.get(CodeValidationStatus.REJECTED, 0),
            )
        )

    recent_rows = db.scalars(
        select(ResponseModel).order_by(ResponseModel.created_at.desc()).limit(10)
    ).all()
    return AdminDashboardStats(
        total_participants=total_participants,
        total_responses=total_responses,
        qualifying_response_count=total_qualifying_responses,
        responses_last_7_days=responses_last_7_days,
        responses_previous_7_days=responses_previous_7_days,
        accepted_code_count=accepted_code_count,
        uncertain_code_count=uncertain_code_count,
        rejected_code_count=rejected_code_count,
        scoring_status_counts=AdminScoringStatusCounts(
            collecting=scoring_counts.get(ResponseScoringStatus.COLLECTING, 0),
            pending_review=scoring_counts.get(ResponseScoringStatus.PENDING_REVIEW, 0),
            provisional=scoring_counts.get(ResponseScoringStatus.PROVISIONAL, 0),
            final=scoring_counts.get(ResponseScoringStatus.FINAL, 0),
            excluded=scoring_counts.get(ResponseScoringStatus.EXCLUDED, 0),
        ),
        daily_stats=daily_stats,
        by_item=by_item,
        recent_responses=[_to_recent(row) for row in recent_rows],
        ai_group_stats=_ai_group_stats(db),
    )


def list_participants_with_stats(db: Session) -> list[AdminParticipantSummary]:
    rows = db.execute(
        select(
            ParticipantModel,
            func.count(ResponseModel.id),
            func.max(ResponseModel.created_at),
        )
        .outerjoin(ResponseModel, ResponseModel.participant_id == ParticipantModel.id)
        .group_by(ParticipantModel.id)
        .order_by(ParticipantModel.created_at.desc())
    ).all()
    return [
        AdminParticipantSummary(
            id=participant.id,
            full_name=participant.full_name,
            email_masked=participant.email_masked,
            email_verified_at=participant.email_verified_at,
            age=participant.age,
            gender=participant.gender,
            occupation=participant.occupation,
            ai_usage_group=participant.ai_usage_group,
            created_at=participant.created_at,
            response_count=count,
            last_submitted_at=last.isoformat() if last else None,
        )
        for participant, count, last in rows
    ]


def get_participant_detail(db: Session, participant_id: str) -> AdminParticipantDetail:
    participant = db.get(ParticipantModel, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người tham gia.")
    rows = db.scalars(
        select(ResponseModel)
        .where(ResponseModel.participant_id == participant_id)
        .order_by(ResponseModel.created_at.desc())
    ).all()
    return AdminParticipantDetail(
        participant=ParticipantOut.model_validate(participant),
        responses=[_to_summary(row) for row in rows],
    )


def _code_counts(
    db: Session,
    item_id: str,
    *,
    code_ids: list[str] | None = None,
    qualifying_only: bool = False,
    scoring_only: bool = False,
) -> dict[str, tuple[int, int, int]]:
    """Đếm bằng chứng mapping; có thể chỉ lấy response đủ điều kiện đóng góp."""
    query = (
        select(
            ResponseIdea.code_id,
            func.count(distinct(ResponseIdea.response_id)),
            func.count(distinct(ResponseModel.participant_id)),
            func.count(ResponseIdea.id),
        )
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .join(ItemCode, ItemCode.id == ResponseIdea.code_id)
        .where(
            ResponseModel.item_id == item_id,
            ResponseIdea.code_id.is_not(None),
            ResponseIdea.mapping_status == "VALID",
        )
        .group_by(ResponseIdea.code_id)
    )
    if qualifying_only:
        query = query.where(
            ResponseModel.scoring_status.notin_(
                [ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED]
            )
        )
    if code_ids is not None:
        if not code_ids:
            return {}
        query = query.where(ResponseIdea.code_id.in_(code_ids))
    if scoring_only:
        query = query.where(
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
        )
    rows = db.execute(query).all()
    return {code_id: (responses, participants, ideas) for code_id, responses, participants, ideas in rows}


def _extraction_exclusion_counts(db: Session, item_id: str) -> dict[str, int]:
    """Đếm riêng ý bị loại ở tầng tách ý, không trộn với quyết định Curator."""
    rows = db.execute(
        select(ResponseIdea.mapping_status, func.count(ResponseIdea.id))
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .where(
            ResponseModel.item_id == item_id,
            ResponseIdea.curator_decision.like("EXTRACTION%"),
            ResponseIdea.mapping_status.in_(["INVALID", "DUPLICATE"]),
        )
        .group_by(ResponseIdea.mapping_status)
    ).all()
    return {status: count for status, count in rows}


def get_extraction_audit(
    db: Session, item_id: str, limit: int = 200
) -> AdminExtractionAudit:
    """Trả nhật ký ý bị Idea Extraction loại để admin có thể kiểm toán."""
    item = db.get(ItemModel, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")

    counts = _extraction_exclusion_counts(db, item_id)
    rows = db.execute(
        select(ResponseIdea, ResponseModel.participant_id)
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .where(
            ResponseModel.item_id == item_id,
            ResponseIdea.curator_decision.like("EXTRACTION%"),
            ResponseIdea.mapping_status.in_(["INVALID", "DUPLICATE"]),
        )
        .order_by(ResponseIdea.created_at.desc(), ResponseIdea.id.desc())
        .limit(limit)
    ).all()
    ideas = [
        AdminExtractionExcludedIdea(
            idea_id=idea.id,
            response_id=idea.response_id,
            participant_id=participant_id,
            original=idea.original,
            normalized=idea.normalized,
            status=idea.mapping_status,
            reason=idea.reason,
            created_at=idea.created_at,
            functional_signature=idea.functional_signature or {},
            mapping_evidence=idea.mapping_evidence or {},
        )
        for idea, participant_id in rows
    ]
    invalid_count = counts.get("INVALID", 0)
    duplicate_count = counts.get("DUPLICATE", 0)
    return AdminExtractionAudit(
        item_id=item.id,
        item_name=item.name,
        invalid_count=invalid_count,
        duplicate_count=duplicate_count,
        total_count=invalid_count + duplicate_count,
        displayed_count=len(ideas),
        ideas=ideas,
    )


def get_curator_audit(
    db: Session, item_id: str, limit: int = 500
) -> AdminCuratorAudit:
    """Trả quyết định Curator hiện tại của từng ý để admin kiểm toán."""
    item = db.get(ItemModel, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")

    curator_decisions = [
        "MATCH_EXISTING",
        "CREATE_NEW",
        "EXPAND_EXISTING",
        "INVALID",
        "UNCERTAIN",
        "OUT_OF_CODEBOOK",
        "POLICY_REJECTED",
        "SCOPE_REJECTED",
        "CURATOR_OBJECT_GUARD",
        "MISSING_DECISION",
    ]
    count_rows = db.execute(
        select(ResponseIdea.curator_decision, func.count(ResponseIdea.id))
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .where(
            ResponseModel.item_id == item_id,
            ResponseIdea.curator_decision.in_(curator_decisions),
        )
        .group_by(ResponseIdea.curator_decision)
    ).all()
    counts = {decision: count for decision, count in count_rows}

    rows = db.execute(
        select(ResponseIdea, ResponseModel.participant_id, ItemCode.name)
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .outerjoin(ItemCode, ItemCode.id == ResponseIdea.code_id)
        .where(
            ResponseModel.item_id == item_id,
            ResponseIdea.curator_decision.in_(curator_decisions),
        )
        .order_by(ResponseIdea.created_at.desc(), ResponseIdea.id.desc())
        .limit(limit)
    ).all()
    decisions = [
        AdminCuratorDecisionIdea(
            idea_id=idea.id,
            response_id=idea.response_id,
            participant_id=participant_id,
            original=idea.original,
            normalized=idea.normalized,
            mapping_status=idea.mapping_status,
            decision=idea.curator_decision,
            code_id=idea.code_id,
            code_name=code_name,
            confidence=idea.confidence,
            reason=idea.reason,
            created_at=idea.created_at,
            functional_signature=idea.functional_signature or {},
            mapping_evidence=idea.mapping_evidence or {},
        )
        for idea, participant_id, code_name in rows
    ]
    match_count = counts.get("MATCH_EXISTING", 0)
    create_count = counts.get("CREATE_NEW", 0)
    expand_count = counts.get("EXPAND_EXISTING", 0)
    invalid_count = counts.get("INVALID", 0)
    guarded_count = counts.get("CURATOR_OBJECT_GUARD", 0) + counts.get(
        "MISSING_DECISION", 0
    ) + counts.get("UNCERTAIN", 0) + counts.get("OUT_OF_CODEBOOK", 0) + counts.get(
        "POLICY_REJECTED", 0
    ) + counts.get(
        "SCOPE_REJECTED", 0
    )
    total_count = match_count + create_count + expand_count + invalid_count + guarded_count
    return AdminCuratorAudit(
        item_id=item.id,
        item_name=item.name,
        match_existing_count=match_count,
        create_new_count=create_count,
        expand_existing_count=expand_count,
        invalid_count=invalid_count,
        guarded_count=guarded_count,
        total_count=total_count,
        displayed_count=len(decisions),
        decisions=decisions,
    )


def _codebook_overview(db: Session, item_id: str) -> AdminCodebookOverview:
    item = db.get(ItemModel, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    participant_count = qualifying_participant_count(db, item_id)
    response_count = qualifying_response_count(db, item_id)
    pending_count = db.scalar(
        select(func.count()).select_from(ResponseIdea).where(
            ResponseIdea.mapping_status == "VALID",
            ResponseIdea.response_id.in_(
                select(ResponseModel.id).where(ResponseModel.item_id == item_id)
            ),
            ResponseIdea.code_id.in_(
                select(ItemCode.id).where(
                    ItemCode.item_id == item_id,
                    ItemCode.validation_status == CodeValidationStatus.UNCERTAIN,
                )
            ),
        )
    ) or 0
    extraction_counts = _extraction_exclusion_counts(db, item_id)
    contributing_idea_count = db.scalar(
        select(func.count(ResponseIdea.id))
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .join(ItemCode, ItemCode.id == ResponseIdea.code_id)
        .where(
            ResponseModel.item_id == item_id,
            ResponseModel.scoring_status.notin_(
                [ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED]
            ),
            ResponseIdea.mapping_status == "VALID",
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
        )
    ) or 0
    accepted_code_count = db.scalar(
        select(func.count()).select_from(ItemCode).where(
            ItemCode.item_id == item_id,
            ItemCode.created_by != "LEGACY",
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
        )
    ) or 0
    rejected_code_count = db.scalar(
        select(func.count()).select_from(ItemCode).where(
            ItemCode.item_id == item_id,
            ItemCode.created_by != "LEGACY",
            ItemCode.validation_status == CodeValidationStatus.REJECTED,
            ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
        )
    ) or 0
    return AdminCodebookOverview(
        item_id=item.id,
        item_name=item.name,
        calibration_status=item.calibration_status.value,
        codebook_epoch=item.codebook_epoch or 0,
        qualifying_response_count=response_count,
        qualifying_participant_count=participant_count,
        contributing_idea_count=contributing_idea_count,
        scoring_min_participants=item.scoring_min_participants,
        scoring_min_ideas=item.scoring_min_ideas,
        pending_idea_count=pending_count,
        extraction_invalid_count=extraction_counts.get("INVALID", 0),
        extraction_duplicate_count=extraction_counts.get("DUPLICATE", 0),
        accepted_code_count=accepted_code_count,
        rejected_code_count=rejected_code_count,
    )


def get_codebook(
    db: Session,
    item_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
    code_filter: str = "ALL",
) -> AdminCodebookSummary:
    """Trả một trang mã; thống kê tổng quan luôn được tính trên toàn bộ sổ mã."""
    overview = _codebook_overview(db, item_id)
    page_size = min(max(page_size, 1), 100)
    conditions = [ItemCode.item_id == item_id, ItemCode.created_by != "LEGACY"]
    if code_filter == "ACCEPTED":
        conditions.extend(
            [
                ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
                ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
            ]
        )
    elif code_filter == "UNCERTAIN":
        conditions.extend(
            [
                ItemCode.validation_status == CodeValidationStatus.UNCERTAIN,
                ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
            ]
        )
    elif code_filter == "REJECTED":
        conditions.extend(
            [
                ItemCode.validation_status == CodeValidationStatus.REJECTED,
                ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
            ]
        )
    elif code_filter != "ALL":
        raise HTTPException(status_code=422, detail="Bộ lọc mã không hợp lệ.")

    code_total = int(
        db.scalar(select(func.count()).select_from(ItemCode).where(*conditions)) or 0
    )
    code_page_count = (code_total + page_size - 1) // page_size
    page = min(max(page, 1), max(code_page_count, 1))
    rows = db.scalars(
        select(ItemCode)
        .where(*conditions)
        .order_by(ItemCode.created_at.desc(), ItemCode.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    merged_target_ids = {row.merged_into_id for row in rows if row.merged_into_id}
    merged_target_names = (
        dict(
            db.execute(
                select(ItemCode.id, ItemCode.name).where(ItemCode.id.in_(merged_target_ids))
            ).all()
        )
        if merged_target_ids
        else {}
    )
    code_ids = [row.id for row in rows]
    # Chỉ tổng hợp bằng chứng cho các mã của trang đang xem.
    counts = _code_counts(db, item_id, code_ids=code_ids)
    contributing_counts = _code_counts(
        db,
        item_id,
        code_ids=code_ids,
        qualifying_only=True,
        scoring_only=True,
    )
    denominator = max(overview.contributing_idea_count, 1)
    codes = []
    for row in rows:
        code_response_count, code_participants, idea_count = counts.get(row.id, (0, 0, 0))
        contributing_responses, contributing_participants, contributing_ideas = contributing_counts.get(
            row.id, (0, 0, 0)
        )
        codes.append(
            AdminCodebookCode(
                id=row.id,
                name=row.name,
                description=row.description,
                validation_status=row.validation_status.value,
                maturity_status=row.maturity_status.value,
                confidence=row.confidence,
                relevance_reason=row.relevance_reason,
                rejection_reason=row.rejection_reason,
                created_by=row.created_by,
                admin_locked=row.admin_locked,
                merged_into_id=row.merged_into_id,
                merged_into_name=merged_target_names.get(row.merged_into_id),
                response_count=code_response_count,
                participant_count=code_participants,
                idea_count=idea_count,
                contributing_response_count=contributing_responses,
                contributing_participant_count=contributing_participants,
                contributing_idea_count=contributing_ideas,
                frequency=contributing_ideas / denominator,
                created_at=row.created_at,
                functional_key=row.functional_key,
                functional_signature=row.functional_signature or {},
                inclusion_rules=row.inclusion_rules or [],
                exclusion_rules=row.exclusion_rules or [],
                positive_examples=row.positive_examples or [],
                embedding_model=row.embedding_model,
                centroid_count=row.centroid_count or 0,
                centroid_revision=row.centroid_revision or 0,
                scope_revision=row.scope_revision or 0,
                drift_flag=row.drift_flag,
                scope_history=row.scope_history or [],
            )
        )
    return AdminCodebookSummary(
        **overview.model_dump(),
        code_page=page,
        code_page_size=page_size,
        code_total=code_total,
        code_page_count=code_page_count,
        codes=codes,
    )


def list_codebooks(db: Session) -> list[AdminCodebookOverview]:
    item_ids = db.scalars(select(ItemModel.id).order_by(ItemModel.name)).all()
    return [_codebook_overview(db, item_id) for item_id in item_ids]


def list_code_options(db: Session, item_id: str) -> list[AdminCodeOption]:
    """Danh sách nhẹ dùng cho thao tác gộp, không tải thống kê của từng mã."""
    if db.get(ItemModel, item_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    rows = db.scalars(
        select(ItemCode)
        .where(
            ItemCode.item_id == item_id,
            ItemCode.created_by != "LEGACY",
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
        )
        .order_by(ItemCode.name, ItemCode.id)
    ).all()
    return [AdminCodeOption(id=row.id, name=row.name) for row in rows]


def _llm_diagnostics(mapping_meta: dict) -> dict:
    """Rút gọn token và thời gian theo stage để admin đọc được, không lộ raw response."""
    stages: list[dict] = []

    def visit(value) -> None:
        if isinstance(value, dict):
            if value.get("stage") and isinstance(value.get("usage"), dict):
                stages.append(
                    {
                        "stage": value.get("stage"),
                        "model": value.get("model"),
                        "attempts": int(value.get("attempts") or 0),
                        "latency_ms": float(value.get("latency_ms") or 0),
                        "usage": value.get("usage") or {},
                        "reasoning_effort": value.get("reasoning_effort"),
                        "failed": bool(value.get("failed")),
                    }
                )
                # attempt_details lặp lại cùng usage nên không đi sâu vào nhánh này.
                for key, nested in value.items():
                    if key not in {"usage", "attempt_details", "raw_response"}:
                        visit(nested)
                return
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(mapping_meta or {})
    usage_keys = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_tokens",
    )
    totals = {
        key: sum(int((stage.get("usage") or {}).get(key) or 0) for stage in stages)
        for key in usage_keys
    }
    return {
        "stages": stages,
        "usage": totals,
        "latency_ms": round(sum(float(stage["latency_ms"]) for stage in stages), 2),
    }


def get_mapping_reviews(
    db: Session,
    item_id: str,
    *,
    status: str = "PENDING",
    limit: int = 200,
) -> AdminMappingReviewList:
    """Hàng đợi ý chưa có mã, kèm snapshot bằng chứng và chi phí AI."""
    item = db.get(ItemModel, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    criteria = (
        ResponseModel.item_id == item_id,
        ResponseIdea.review_status == status,
    )
    total_count = int(
        db.scalar(
            select(func.count(ResponseIdea.id))
            .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
            .where(*criteria)
        )
        or 0
    )
    pending_count = int(
        db.scalar(
            select(func.count(ResponseIdea.id))
            .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
            .where(
                ResponseModel.item_id == item_id,
                ResponseIdea.review_status == "PENDING",
            )
        )
        or 0
    )
    rows = db.execute(
        select(ResponseIdea, ResponseModel)
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .where(*criteria)
        .order_by(ResponseIdea.created_at, ResponseIdea.id)
        .limit(limit)
    ).all()
    return AdminMappingReviewList(
        item_id=item.id,
        item_name=item.name,
        pending_count=pending_count,
        total_count=total_count,
        code_options=list_code_options(db, item_id),
        reviews=[
            AdminMappingReviewIdea(
                idea_id=idea.id,
                response_id=response.id,
                participant_id=response.participant_id,
                original=idea.original,
                normalized=idea.normalized,
                decision=idea.curator_decision,
                confidence=idea.confidence,
                reason=idea.reason,
                review_status=idea.review_status,
                review_payload=idea.review_payload or {},
                functional_signature=idea.functional_signature or {},
                mapping_evidence=idea.mapping_evidence or {},
                ai_diagnostics=_llm_diagnostics(response.mapping_meta or {}),
                created_at=idea.created_at,
            )
            for idea, response in rows
        ],
    )


def _mapping_from_ideas(ideas: list[ResponseIdea]) -> dict:
    """Dựng lại JSON hiển thị từ các hàng chuẩn sau quyết định của admin."""
    return MappingResult(
        ideas=[
            MappedIdea(
                original=idea.original,
                normalized=idea.normalized,
                code=idea.code.name if idea.code else None,
                status=idea.mapping_status,
                is_valid=idea.mapping_status == "VALID" and idea.code is not None,
                reason=idea.reason,
                line_index=idea.line_index,
                functional_signature=idea.functional_signature or {},
                curator_decision=idea.curator_decision,
            )
            for idea in sorted(ideas, key=lambda row: (row.line_index, row.id))
        ]
    ).model_dump()


def _clean_rules(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys(" ".join(value.split()) for value in values or [] if value.strip()))


def _rebuild_code_centroid(db: Session, code: ItemCode) -> None:
    members = db.execute(
        select(ResponseIdea.embedding, ResponseIdea.embedding_model)
        .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
        .where(
            ResponseIdea.code_id == code.id,
            ResponseIdea.mapping_status == "VALID",
            ResponseModel.scoring_status != ResponseScoringStatus.EXCLUDED,
        )
    ).all()
    rebuild_confirmed_members(
        code,
        [(embedding or [], model or "") for embedding, model in members],
        drift_cosine_floor=settings.centroid_drift_cosine_floor,
    )


def resolve_mapping_review(
    db: Session,
    item_id: str,
    idea_id: str,
    resolution: AdminMappingReviewResolution,
    admin: UserModel,
) -> AdminMappingReviewResult:
    """Áp quyết định con người dưới khóa item và lưu đầy đủ dấu vết kiểm toán."""
    item = db.scalar(select(ItemModel).where(ItemModel.id == item_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    idea = db.scalar(
        select(ResponseIdea).where(ResponseIdea.id == idea_id).with_for_update()
    )
    if idea is None or idea.response.item_id != item_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy ý cần phân xử.")
    if idea.review_status != "PENDING":
        raise HTTPException(status_code=409, detail="Ý này đã được phân xử trước đó.")
    response = db.scalar(
        select(ResponseModel).where(ResponseModel.id == idea.response_id).with_for_update()
    )
    if response.scoring_status == ResponseScoringStatus.FINAL:
        raise HTTPException(status_code=409, detail="Không thay đổi mapping của điểm đã chốt.")
    if (
        resolution.expected_codebook_epoch is not None
        and resolution.expected_codebook_epoch != (item.codebook_epoch or 0)
    ):
        raise HTTPException(
            status_code=409,
            detail="Sổ mã vừa thay đổi. Hãy tải lại căn cứ trước khi xác nhận.",
        )

    proposal = dict((idea.review_payload or {}).get("proposal") or {})
    selected_code: ItemCode | None = None
    now = datetime.now(timezone.utc)
    admin_id = getattr(admin, "id", None)

    if resolution.action == "MATCH_EXISTING":
        selected_code = db.scalar(
            select(ItemCode)
            .where(
                ItemCode.id == resolution.existing_code_id,
                ItemCode.item_id == item_id,
                ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
                ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
            )
            .with_for_update()
        )
        if selected_code is None:
            raise HTTPException(status_code=409, detail="Mã được chọn không còn hoạt động.")
        idea.mapping_status = "VALID"
        idea.curator_decision = "ADMIN_MATCH_EXISTING"
        idea.reason = resolution.note or "Quản trị viên đã gán vào mã hiện có."
    elif resolution.action == "CREATE_NEW":
        signature = (
            resolution.functional_signature.model_dump()
            if resolution.functional_signature is not None
            else proposal.get("functional_signature") or idea.functional_signature or {}
        )
        signature_key = functional_key(signature)
        if not all(part for part in signature_key.split("|")):
            raise HTTPException(
                status_code=422,
                detail="Mã mới phải có đủ mục đích, vai trò của vật và cơ chế.",
            )
        name = " ".join((resolution.code_name or proposal.get("code_name") or "").split())
        description = " ".join(
            (resolution.code_description or proposal.get("code_description") or "").split()
        )
        inclusion_rules = _clean_rules(
            resolution.inclusion_rules
            if resolution.inclusion_rules is not None
            else proposal.get("inclusion_rules")
        )
        exclusion_rules = _clean_rules(
            resolution.exclusion_rules
            if resolution.exclusion_rules is not None
            else proposal.get("exclusion_rules")
        )
        positive_examples = _clean_rules(
            resolution.positive_examples
            if resolution.positive_examples is not None
            else [*(proposal.get("positive_examples") or []), idea.original]
        )
        if len(name) < 2 or not description:
            raise HTTPException(status_code=422, detail="Cần tên và mô tả cho mã mới.")
        if not inclusion_rules or not exclusion_rules:
            raise HTTPException(
                status_code=422,
                detail="Cần ít nhất một quy tắc bao gồm và một phản ví dụ loại trừ.",
            )
        normalized_name = normalize_code_name(name)
        collision = db.scalar(
            select(ItemCode).where(
                ItemCode.item_id == item_id,
                ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
                or_(
                    ItemCode.normalized_name == normalized_name,
                    ItemCode.functional_key == signature_key,
                ),
            )
        )
        if collision is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f'Mã mới va với “{collision.name}”. Hãy tải lại và dùng thao tác gán mã hiện có.'
                ),
            )
        reviewed_vector = local_embedding(core_signature_text(signature))
        reviewed_model = active_embedding_model(None)
        selected_code = ItemCode(
            id=str(uuid.uuid4()),
            item_id=item_id,
            name=name,
            normalized_name=normalized_name,
            description=description,
            functional_key=signature_key,
            functional_signature=signature,
            inclusion_rules=inclusion_rules,
            exclusion_rules=exclusion_rules,
            positive_examples=positive_examples,
            embedding=reviewed_vector,
            embedding_model=reviewed_model,
            validation_status=CodeValidationStatus.ACCEPTED,
            maturity_status=CodeMaturityStatus.ACTIVE,
            confidence=1.0,
            relevance_reason=resolution.note or "Mã được quản trị viên xác nhận từ hàng đợi phân xử.",
            source_response_id=response.id,
            created_by="ADMIN",
            admin_locked=True,
            reviewed_by=admin_id,
            reviewed_at=now,
            scope_history=[],
        )
        db.add(selected_code)
        item.codebook_epoch = (item.codebook_epoch or 0) + 1
        idea.functional_signature = signature
        idea.embedding = reviewed_vector
        idea.embedding_model = reviewed_model
        idea.mapping_status = "VALID"
        idea.curator_decision = "ADMIN_CREATE_NEW"
        idea.reason = resolution.note or "Quản trị viên đã duyệt tạo mã mới."
    else:
        idea.mapping_status = "INVALID"
        idea.curator_decision = "ADMIN_MARK_INVALID"
        idea.reason = resolution.note or "Quản trị viên xác định ý không có nghĩa để mã hóa."

    idea.code = selected_code
    idea.review_status = "RESOLVED"
    idea.review_resolution = resolution.action
    idea.review_note = resolution.note
    idea.reviewed_by = admin_id
    idea.reviewed_at = now
    idea.mapping_evidence = {
        **(idea.mapping_evidence or {}),
        "admin_resolution": {
            "action": resolution.action,
            "reviewed_by": admin_id,
            "reviewed_at": now.isoformat(),
            "note": resolution.note,
            "codebook_epoch": item.codebook_epoch or 0,
            "code_id": selected_code.id if selected_code else None,
        },
    }
    db.flush()
    if selected_code is not None:
        _rebuild_code_centroid(db, selected_code)

    remaining = int(
        db.scalar(
            select(func.count(ResponseIdea.id)).where(
                ResponseIdea.response_id == response.id,
                ResponseIdea.review_status == "PENDING",
            )
        )
        or 0
    )
    response.mapping = _mapping_from_ideas(list(response.ideas))
    response.scoring = {}
    response.scoring_meta = {"invalidated_by": "ADMIN_MAPPING_REVIEW"}
    response.fluency = 0
    response.flexibility = 0
    response.originality = 0
    response.elaboration = 0
    response.scored_at = None
    response.scoring_status = (
        ResponseScoringStatus.PENDING_REVIEW
        if remaining
        else ResponseScoringStatus.COLLECTING
    )
    response.processing_state = "DONE"
    response.processing_attempts = 0
    response.processing_claim_token = None
    response.processing_lease_until = None
    response.processing_error = ""
    refresh_item_scoring_state(db, item)
    if item_is_ready_for_scoring(db, item):
        refresh_final_frequency_scores(db, item_id)
    db.commit()
    return AdminMappingReviewResult(
        idea_id=idea.id,
        response_id=response.id,
        resolution=resolution.action,
        code_id=selected_code.id if selected_code else None,
        code_name=selected_code.name if selected_code else None,
        scoring_status=response.scoring_status.value,
    )


def remap_item(item_id: str) -> int:
    """Sổ mã append-only không cho phép thay đổi điểm đã chốt bằng remap thủ công."""
    raise HTTPException(
        status_code=409,
        detail="Sổ mã đang chạy trực tiếp và bất biến; không hỗ trợ phân loại lại dữ liệu cũ.",
    )


def _refresh_after_admin_change(db: Session, item: ItemModel) -> None:
    """Cập nhật trạng thái ngưỡng mà không tự ghi đè bất kỳ điểm FINAL nào."""
    db.flush()
    refresh_item_scoring_state(db, item)


def _update_mapping_after_code_decision(
    mapping: dict,
    source_name: str,
    *,
    replacement_name: str | None = None,
    reject: bool = False,
) -> dict:
    """Đồng bộ JSON hiển thị sau khi admin chấp nhận, gộp hoặc loại một mã."""
    payload = dict(mapping or {})
    ideas = []
    for idea in payload.get("ideas", []):
        copied = dict(idea)
        if copied.get("code") == source_name:
            if reject:
                if replacement_name:
                    copied["code"] = replacement_name
                copied["status"] = "INVALID"
                copied["is_valid"] = False
                copied["reason"] = "Quản trị viên xác định mã này không hợp lệ."
            elif replacement_name:
                copied["code"] = replacement_name
                copied["status"] = "VALID"
                copied["is_valid"] = True
                copied["reason"] = "Quản trị viên đã gộp ý này vào mã phù hợp."
        ideas.append(copied)
    payload["ideas"] = ideas
    return payload


def _response_still_has_uncertain_idea(response: ResponseModel) -> bool:
    """Kiểm tra một lượt còn ý nào chưa đủ căn cứ để đưa vào chấm điểm hay không."""
    for idea in response.ideas:
        if idea.mapping_status != "VALID":
            continue
        if idea.code is None:
            return True
        if idea.code.validation_status == CodeValidationStatus.UNCERTAIN:
            return True
    return False


def _record_final_codebook_change(
    response: ResponseModel,
    change_type: str,
    details: dict | None = None,
) -> None:
    """Ghi dấu vết thay đổi codebook nhưng không làm thay đổi snapshot điểm FINAL."""
    changed_at = datetime.now(timezone.utc).isoformat()
    meta = dict(response.scoring_meta or {})
    changes = list(meta.get("codebook_changes", []))
    changes.append(
        {
            "type": change_type,
            "changed_at": changed_at,
            **(details or {}),
        }
    )
    meta["codebook_changes"] = changes
    meta["codebook_changed_after_scoring_at"] = changed_at
    meta.pop("requires_manual_rescore", None)
    response.scoring_meta = meta


def _reset_responses_after_code_decision(
    db: Session,
    response_ids: list[str],
    source_name: str,
    *,
    replacement_name: str | None = None,
    reject: bool = False,
    preserve_final_mapping: bool = False,
    final_change_type: str = "ADMIN_CODE_DECISION",
    final_change_details: dict | None = None,
) -> None:
    """Cập nhật lượt chưa chấm và giữ nguyên snapshot của lượt FINAL khi cần."""
    if not response_ids:
        return
    rows = db.scalars(
        select(ResponseModel).where(ResponseModel.id.in_(response_ids))
    ).all()
    db.flush()
    for row in rows:
        if row.scoring_status == ResponseScoringStatus.FINAL and preserve_final_mapping:
            _record_final_codebook_change(
                row,
                final_change_type,
                final_change_details,
            )
            continue
        row.mapping = _update_mapping_after_code_decision(
            row.mapping,
            source_name,
            replacement_name=replacement_name,
            reject=reject,
        )
        if row.scoring_status == ResponseScoringStatus.FINAL:
            _record_final_codebook_change(
                row,
                final_change_type,
                final_change_details,
            )
            continue
        row.scoring = {}
        row.scoring_meta = {"invalidated_by": "ADMIN_CODE_DECISION"}
        row.fluency = 0
        row.flexibility = 0
        row.originality = 0
        row.elaboration = 0
        row.scored_at = None
        row.scoring_status = (
            ResponseScoringStatus.PENDING_REVIEW
            if _response_still_has_uncertain_idea(row)
            else ResponseScoringStatus.COLLECTING
        )


def patch_code(db: Session, item_id: str, code_id: str, patch: AdminCodePatch) -> AdminCodebookSummary:
    item = db.get(ItemModel, item_id)
    code = db.get(ItemCode, code_id)
    if item is None or code is None or code.item_id != item_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy code của đồ vật.")
    raise HTTPException(
        status_code=409,
        detail="Mã đã được dùng để tính điểm là bất biến; quản trị chỉ có quyền kiểm toán.",
    )
    if code.maturity_status == CodeMaturityStatus.MERGED:
        raise HTTPException(status_code=409, detail="Mã đã gộp chỉ được giữ để truy vết.")
    changes = patch.model_dump(exclude_unset=True)
    forbidden = set(changes) - {"name"}
    if forbidden:
        raise HTTPException(
            status_code=409,
            detail="Mã đã dùng để tính điểm là bất biến; chỉ được sửa nhãn hiển thị.",
        )
    original_name = code.name
    previous_status = code.validation_status
    affected_response_ids = list(
        db.scalars(
            select(ResponseIdea.response_id)
            .where(ResponseIdea.code_id == code_id)
            .distinct()
        ).all()
    )
    if "name" in changes:
        normalized = normalize_code_name(changes["name"])
        duplicate = db.scalar(
            select(ItemCode).where(
                ItemCode.item_id == item_id,
                ItemCode.normalized_name == normalized,
                ItemCode.id != code_id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Tên code đã tồn tại; hãy dùng thao tác gộp.")
        code.name = changes["name"].strip()
        code.normalized_name = normalized
    if "description" in changes:
        code.description = changes["description"].strip()
    if "validation_status" in changes:
        code.validation_status = CodeValidationStatus(changes["validation_status"])
        code.admin_locked = True
        code.rejection_reason = (
            "Quản trị viên xác định mã này không hợp lệ."
            if code.validation_status == CodeValidationStatus.REJECTED
            else ""
        )
        if (
            previous_status == CodeValidationStatus.UNCERTAIN
            and code.validation_status == CodeValidationStatus.REJECTED
        ):
            db.execute(
                update(ResponseIdea)
                .where(
                    ResponseIdea.code_id == code_id,
                    ResponseIdea.mapping_status == "VALID",
                )
                .values(mapping_status="INVALID")
            )
    if "admin_locked" in changes:
        code.admin_locked = changes["admin_locked"]
    code.reviewed_at = datetime.now(timezone.utc)
    if "validation_status" in changes or "name" in changes:
        _reset_responses_after_code_decision(
            db,
            affected_response_ids,
            original_name,
            replacement_name=code.name if "name" in changes else None,
            reject=code.validation_status == CodeValidationStatus.REJECTED,
        )
    _refresh_after_admin_change(db, item)
    if item_is_ready_for_scoring(db, item):
        reprocess_item_scores_in_session(db, item_id)
    db.commit()
    return get_codebook(db, item_id)


def merge_code(db: Session, item_id: str, source_id: str, target_id: str) -> AdminCodebookSummary:
    raise HTTPException(
        status_code=409,
        detail="Sổ mã append-only không hỗ trợ gộp mã sau khi đã tính điểm.",
    )
    item = db.get(ItemModel, item_id)
    if source_id == target_id:
        raise HTTPException(status_code=400, detail="Không thể gộp một code vào chính nó.")
    locked_codes = db.scalars(
        select(ItemCode)
        .where(ItemCode.id.in_([source_id, target_id]))
        .with_for_update()
    ).all()
    codes_by_id = {code.id: code for code in locked_codes}
    source = codes_by_id.get(source_id)
    target = codes_by_id.get(target_id)
    if item is None or source is None or target is None or source.item_id != item_id or target.item_id != item_id:
        raise HTTPException(status_code=404, detail="Code nguồn hoặc code đích không hợp lệ.")
    if source.maturity_status != CodeMaturityStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Mã nguồn đã được gộp trước đó.")
    if source.validation_status not in {
        CodeValidationStatus.ACCEPTED,
        CodeValidationStatus.UNCERTAIN,
    }:
        raise HTTPException(status_code=409, detail="Mã nguồn đã bị loại nên không thể gộp.")
    if (
        target.maturity_status != CodeMaturityStatus.ACTIVE
        or target.validation_status != CodeValidationStatus.ACCEPTED
    ):
        raise HTTPException(
            status_code=409,
            detail="Mã đích phải là mã đang hoạt động và đã được chấp nhận.",
        )
    affected_response_ids = list(
        db.scalars(
            select(ResponseIdea.response_id)
            .where(ResponseIdea.code_id == source.id)
            .distinct()
        ).all()
    )
    db.execute(update(ResponseIdea).where(ResponseIdea.code_id == source.id).values(code_id=target.id))
    # Làm phẳng chuỗi gộp: mọi mã từng gộp vào nguồn sẽ trỏ thẳng tới đích mới.
    db.execute(
        update(ItemCode)
        .where(ItemCode.merged_into_id == source.id)
        .values(merged_into_id=target.id)
    )
    reviewed_at = datetime.now(timezone.utc)
    source.maturity_status = CodeMaturityStatus.MERGED
    source.merged_into_id = target.id
    source.admin_locked = True
    source.reviewed_at = reviewed_at
    target.admin_locked = True
    target.reviewed_at = reviewed_at
    _reset_responses_after_code_decision(
        db,
        affected_response_ids,
        source.name,
        replacement_name=target.name,
        preserve_final_mapping=True,
        final_change_type="CODE_MERGE",
        final_change_details={
            "source_code_id": source.id,
            "source_code_name": source.name,
            "target_code_id": target.id,
            "target_code_name": target.name,
        },
    )
    _refresh_after_admin_change(db, item)
    if item_is_ready_for_scoring(db, item):
        reprocess_item_scores_in_session(db, item_id)
    db.commit()
    return get_codebook(db, item_id)


def _mapping_without_code(mapping: dict, code_name: str | None = None) -> dict:
    """Bỏ liên kết code trong JSON hiển thị nhưng giữ nguyên câu gốc và câu chuẩn hoá."""
    payload = dict(mapping or {})
    ideas = []
    for idea in payload.get("ideas", []):
        copied = dict(idea)
        if code_name is None or copied.get("code") == code_name:
            copied["code"] = None
            copied["is_valid"] = False
            copied["reason"] = "Code đã bị admin xoá; ý đang chờ phân loại lại."
        ideas.append(copied)
    payload["ideas"] = ideas
    return payload


def _reset_affected_response(row: ResponseModel, code_name: str) -> None:
    """Giữ điểm FINAL bất biến; lượt chưa chấm quay về chờ phân loại lại."""
    row.mapping = _mapping_without_code(row.mapping, code_name)
    if row.scoring_status == ResponseScoringStatus.FINAL:
        _record_final_codebook_change(
            row,
            "CODE_DELETE",
            {"deleted_code_name": code_name},
        )
        return
    row.scoring = {}
    row.scoring_meta = {"invalidated_by": "ADMIN_CODE_DELETE"}
    row.fluency = 0
    row.flexibility = 0
    row.originality = 0
    row.elaboration = 0
    row.scoring_status = ResponseScoringStatus.PENDING_REVIEW
    row.scored_at = None


def delete_code(db: Session, item_id: str, code_id: str) -> AdminCodebookSummary:
    """Xoá cứng một code; response gốc vẫn được giữ và chuyển sang chờ phân loại lại."""
    raise HTTPException(
        status_code=409,
        detail="Mã đã dùng để tính điểm là bất biến và không thể xoá.",
    )
    item = db.get(ItemModel, item_id)
    code = db.get(ItemCode, code_id)
    if item is None or code is None or code.item_id != item_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy code của đồ vật.")
    if code.maturity_status == CodeMaturityStatus.MERGED:
        raise HTTPException(status_code=409, detail="Mã đã gộp chỉ được giữ để truy vết.")
    merged_source_exists = db.scalar(
        select(ItemCode.id).where(ItemCode.merged_into_id == code_id).limit(1)
    )
    if merged_source_exists:
        raise HTTPException(
            status_code=409,
            detail="Không thể xoá mã đích khi vẫn còn mã khác đã gộp vào mã này.",
        )

    response_ids = list(
        db.scalars(
            select(ResponseIdea.response_id)
            .where(ResponseIdea.code_id == code_id)
            .distinct()
        ).all()
    )
    affected_responses = (
        db.scalars(select(ResponseModel).where(ResponseModel.id.in_(response_ids))).all()
        if response_ids
        else []
    )

    db.execute(
        update(ResponseIdea)
        .where(ResponseIdea.code_id == code_id)
        .values(
            code_id=None,
            curator_decision="ADMIN_DELETED",
            confidence=0,
            reason="Code đã bị admin xoá; chờ phân loại lại.",
        )
    )
    for response in affected_responses:
        _reset_affected_response(response, code.name)

    db.delete(code)
    db.flush()
    _refresh_after_admin_change(db, item)
    db.commit()
    return get_codebook(db, item_id)


def delete_all_codes(db: Session, item_id: str) -> AdminCodebookSummary:
    raise HTTPException(
        status_code=409,
        detail="Sổ mã append-only không hỗ trợ xoá mã sau khi đã tính điểm.",
    )
    """Đặt lại codebook của một đồ vật mà không xoá raw response của nghiên cứu."""
    item = db.get(ItemModel, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")

    affected_responses = db.scalars(
        select(ResponseModel).where(ResponseModel.item_id == item_id)
    ).all()
    for response in affected_responses:
        response.mapping = _mapping_without_code(response.mapping)
        response.scoring = {}
        response.scoring_meta = {"invalidated_by": "ADMIN_CODEBOOK_RESET"}
        response.fluency = 0
        response.flexibility = 0
        response.originality = 0
        response.elaboration = 0
        response.scoring_status = ResponseScoringStatus.COLLECTING
        response.scored_at = None
    db.execute(
        delete(ResponseIdea).where(
            ResponseIdea.response_id.in_(
                select(ResponseModel.id).where(ResponseModel.item_id == item_id)
            )
        )
    )
    db.execute(update(ItemCode).where(ItemCode.item_id == item_id).values(merged_into_id=None))
    db.execute(delete(ItemCode).where(ItemCode.item_id == item_id))

    item.calibration_status = ItemCalibrationStatus.COLLECTING
    db.commit()
    return get_codebook(db, item_id)
