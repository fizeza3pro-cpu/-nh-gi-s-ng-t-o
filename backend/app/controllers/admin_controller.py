"""Nghiệp vụ thống kê dành riêng cho quản trị viên."""

import csv
import io

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
)
from app.pipeline.codebook_service import (
    item_is_ready_for_scoring,
    refresh_item_scoring_state,
    qualifying_idea_count,
    qualifying_participant_count,
    qualifying_response_count,
)
from app.pipeline.dynamic_mapping import normalize_code_name
from app.controllers.response_controller import (
    reprocess_item_mappings,
    reprocess_item_scores_in_session,
)
from app.models.models import Participant as ParticipantModel
from app.models.models import Response as ResponseModel
from app.schemas.schemas import (
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
    AdminScoringStatusCounts,
    ParticipantOut,
    ResponseSummary,
)


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
        ]
    )
    for response, participant, item in rows:
        has_final_score = response.scoring_status == ResponseScoringStatus.FINAL
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
            ]
        )
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
