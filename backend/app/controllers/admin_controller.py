"""Nghiệp vụ thống kê dành riêng cho quản trị viên."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, distinct, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Item as ItemModel
from app.models.models import (
    CodebookVersion,
    CodebookVersionCode,
    CodeMaturityStatus,
    CodeValidationStatus,
    ItemCode,
    ItemCalibrationStatus,
    ResponseIdea,
    ResponseScoringStatus,
)
from app.pipeline.codebook_service import (
    create_codebook_version,
    eligible_participant_count,
    eligible_response_count as count_eligible_responses,
    mark_item_for_recalculation,
)
from app.pipeline.dynamic_mapping import normalize_code_name
from app.controllers.response_controller import (
    reprocess_item_mappings,
    reprocess_item_scores,
    reprocess_item_scores_in_session,
)
from app.models.models import Participant as ParticipantModel
from app.models.models import Response as ResponseModel
from app.schemas.schemas import (
    AdminDailyStat,
    AdminDashboardStats,
    AdminItemBreakdown,
    AdminCodePatch,
    AdminCodebookCode,
    AdminCodebookSummary,
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


def get_dashboard_stats(db: Session) -> AdminDashboardStats:
    """Tổng hợp tiến độ thu thập dữ liệu và hiệu chỉnh codebook động."""
    total_participants = db.scalar(select(func.count()).select_from(ParticipantModel)) or 0
    total_responses = db.scalar(select(func.count()).select_from(ResponseModel)) or 0
    total_eligible_responses = db.scalar(
        select(func.count()).select_from(ResponseModel).where(
            ResponseModel.calibration_eligible.is_(True)
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
        active_version = (
            db.get(CodebookVersion, item.active_codebook_version_id)
            if item.active_codebook_version_id
            else None
        )
        by_item.append(
            AdminItemBreakdown(
                item_id=item.id,
                item_name=item.name,
                response_count=response_count,
                calibration_status=item.calibration_status.value,
                eligible_response_count=count_eligible_responses(db, item.id),
                eligible_participant_count=eligible_participant_count(db, item.id),
                calibration_min_participants=item.calibration_min_participants,
                originality_min_participants=item.originality_min_participants,
                accepted_code_count=item_code_counts.get(CodeValidationStatus.ACCEPTED, 0),
                uncertain_code_count=item_code_counts.get(CodeValidationStatus.UNCERTAIN, 0),
                rejected_code_count=item_code_counts.get(CodeValidationStatus.REJECTED, 0),
                active_version=active_version.version if active_version else None,
            )
        )

    recent_rows = db.scalars(
        select(ResponseModel).order_by(ResponseModel.created_at.desc()).limit(10)
    ).all()
    return AdminDashboardStats(
        total_participants=total_participants,
        total_responses=total_responses,
        eligible_response_count=total_eligible_responses,
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
            email_masked=participant.email_masked,
            email_verified_at=participant.email_verified_at,
            age=participant.age,
            gender=participant.gender,
            occupation=participant.occupation,
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
    calibration_only: bool = False,
    scoring_only: bool = False,
) -> dict[str, tuple[int, int, int]]:
    """Đếm bằng chứng mapping; tuỳ chọn chỉ lấy các lượt thuộc mẫu hiệu chuẩn."""
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
    if calibration_only:
        query = query.where(ResponseModel.calibration_eligible.is_(True))
    if scoring_only:
        query = query.where(
            or_(
                ResponseIdea.confidence >= settings.code_uncertain_confidence,
                ItemCode.admin_locked.is_(True),
            ),
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status.in_(
                [CodeMaturityStatus.EMERGING, CodeMaturityStatus.STABLE]
            ),
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
        "INVALID",
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
        )
        for idea, participant_id, code_name in rows
    ]
    match_count = counts.get("MATCH_EXISTING", 0)
    create_count = counts.get("CREATE_NEW", 0)
    invalid_count = counts.get("INVALID", 0)
    guarded_count = counts.get("CURATOR_OBJECT_GUARD", 0) + counts.get(
        "MISSING_DECISION", 0
    )
    total_count = match_count + create_count + invalid_count + guarded_count
    return AdminCuratorAudit(
        item_id=item.id,
        item_name=item.name,
        match_existing_count=match_count,
        create_new_count=create_count,
        invalid_count=invalid_count,
        guarded_count=guarded_count,
        total_count=total_count,
        displayed_count=len(decisions),
        decisions=decisions,
    )


def get_codebook(db: Session, item_id: str) -> AdminCodebookSummary:
    item = db.get(ItemModel, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    participant_count = eligible_participant_count(db, item_id)
    sample_response_count = count_eligible_responses(db, item_id)
    # Admin cần thấy đồng thời tổng bằng chứng, số lượt thuộc mẫu chuẩn và số người khác nhau.
    counts = _code_counts(db, item_id)
    eligible_counts = _code_counts(
        db, item_id, calibration_only=True, scoring_only=True
    )
    rows = db.scalars(
        select(ItemCode)
        .where(ItemCode.item_id == item_id)
        .order_by(ItemCode.created_at.desc())
    ).all()
    active_version = db.get(CodebookVersion, item.active_codebook_version_id) if item.active_codebook_version_id else None
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
    sample_idea_count = sum(
        idea_count for _, _, idea_count in eligible_counts.values()
    )
    denominator = max(sample_idea_count, 1)
    codes = []
    for row in rows:
        code_response_count, code_participants, idea_count = counts.get(row.id, (0, 0, 0))
        eligible_responses, eligible_participants, eligible_ideas = eligible_counts.get(
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
                response_count=code_response_count,
                participant_count=code_participants,
                idea_count=idea_count,
                eligible_response_count=eligible_responses,
                eligible_participant_count=eligible_participants,
                eligible_idea_count=eligible_ideas,
                frequency=eligible_ideas / denominator,
                created_at=row.created_at,
            )
        )
    return AdminCodebookSummary(
        item_id=item.id,
        item_name=item.name,
        calibration_status=item.calibration_status.value,
        eligible_response_count=sample_response_count,
        eligible_participant_count=participant_count,
        eligible_idea_count=sample_idea_count,
        calibration_min_participants=item.calibration_min_participants,
        originality_min_participants=item.originality_min_participants,
        active_version=active_version.version if active_version else None,
        pending_idea_count=pending_count,
        extraction_invalid_count=extraction_counts.get("INVALID", 0),
        extraction_duplicate_count=extraction_counts.get("DUPLICATE", 0),
        accepted_code_count=sum(code.validation_status == "ACCEPTED" and code.maturity_status not in {"ARCHIVED", "MERGED"} for code in codes),
        rejected_code_count=sum(code.validation_status == "REJECTED" for code in codes),
        codes=codes,
    )


def list_codebooks(db: Session) -> list[AdminCodebookSummary]:
    item_ids = db.scalars(select(ItemModel.id).order_by(ItemModel.name)).all()
    return [get_codebook(db, item_id) for item_id in item_ids]


def remap_item(item_id: str) -> int:
    """Cho admin chủ động chạy lại cả hai tầng mapping của một đồ vật."""
    return reprocess_item_mappings(item_id)


def _refresh_after_admin_change(db: Session, item: ItemModel) -> None:
    """Đóng version mới ngay để thao tác admin không sửa ngầm snapshot cũ."""
    mark_item_for_recalculation(db, item.id)
    if item.active_codebook_version_id:
        item.calibration_status = ItemCalibrationStatus.RECALIBRATING
        create_codebook_version(db, item, eligible_participant_count(db, item.id))


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
        if (
            idea.code.validation_status == CodeValidationStatus.ACCEPTED
            and idea.confidence < settings.code_uncertain_confidence
            and not idea.code.admin_locked
        ):
            return True
    return False


def _reset_responses_after_code_decision(
    db: Session,
    response_ids: list[str],
    source_name: str,
    *,
    replacement_name: str | None = None,
    reject: bool = False,
) -> None:
    """Bỏ điểm cũ và giải phóng PENDING khi quyết định admin đã đủ rõ."""
    if not response_ids:
        return
    rows = db.scalars(
        select(ResponseModel).where(ResponseModel.id.in_(response_ids))
    ).all()
    db.flush()
    for row in rows:
        row.mapping = _update_mapping_after_code_decision(
            row.mapping,
            source_name,
            replacement_name=replacement_name,
            reject=reject,
        )
        row.scoring = {}
        row.scoring_meta = {"invalidated_by": "ADMIN_CODE_DECISION"}
        row.fluency = 0
        row.flexibility = 0
        row.originality = 0
        row.elaboration = 0
        row.codebook_version_id = None
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
    changes = patch.model_dump(exclude_unset=True)
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
    if item.active_codebook_version_id:
        reprocess_item_scores_in_session(db, item_id)
    db.commit()
    return get_codebook(db, item_id)


def archive_code(db: Session, item_id: str, code_id: str, restore: bool = False) -> AdminCodebookSummary:
    item = db.get(ItemModel, item_id)
    code = db.get(ItemCode, code_id)
    if item is None or code is None or code.item_id != item_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy code của đồ vật.")
    code.maturity_status = CodeMaturityStatus.EMERGING if restore else CodeMaturityStatus.ARCHIVED
    code.admin_locked = True
    code.reviewed_at = datetime.now(timezone.utc)
    _refresh_after_admin_change(db, item)
    db.commit()
    return get_codebook(db, item_id)


def merge_code(db: Session, item_id: str, source_id: str, target_id: str) -> AdminCodebookSummary:
    item = db.get(ItemModel, item_id)
    source = db.get(ItemCode, source_id)
    target = db.get(ItemCode, target_id)
    if item is None or source is None or target is None or source.item_id != item_id or target.item_id != item_id:
        raise HTTPException(status_code=404, detail="Code nguồn hoặc code đích không hợp lệ.")
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Không thể gộp một code vào chính nó.")
    affected_response_ids = list(
        db.scalars(
            select(ResponseIdea.response_id)
            .where(ResponseIdea.code_id == source.id)
            .distinct()
        ).all()
    )
    db.execute(update(ResponseIdea).where(ResponseIdea.code_id == source.id).values(code_id=target.id))
    source.maturity_status = CodeMaturityStatus.MERGED
    source.merged_into_id = target.id
    source.admin_locked = True
    target.admin_locked = True
    target.reviewed_at = datetime.now(timezone.utc)
    _reset_responses_after_code_decision(
        db,
        affected_response_ids,
        source.name,
        replacement_name=target.name,
    )
    _refresh_after_admin_change(db, item)
    if item.active_codebook_version_id:
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
    """Không để điểm cũ tiếp tục xuất hiện sau khi code cấu thành điểm đã bị xoá."""
    row.mapping = _mapping_without_code(row.mapping, code_name)
    row.scoring = {}
    row.scoring_meta = {"invalidated_by": "ADMIN_CODE_DELETE"}
    row.fluency = 0
    row.flexibility = 0
    row.originality = 0
    row.elaboration = 0
    row.scoring_status = ResponseScoringStatus.PENDING_REVIEW
    row.codebook_version_id = None
    row.scored_at = None


def delete_code(db: Session, item_id: str, code_id: str) -> AdminCodebookSummary:
    """Xoá cứng một code; response gốc vẫn được giữ và chuyển sang chờ phân loại lại."""
    item = db.get(ItemModel, item_id)
    code = db.get(ItemCode, code_id)
    if item is None or code is None or code.item_id != item_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy code của đồ vật.")

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
    db.execute(delete(CodebookVersionCode).where(CodebookVersionCode.code_id == code_id))
    db.execute(
        update(ItemCode)
        .where(ItemCode.merged_into_id == code_id)
        .values(merged_into_id=None, maturity_status=CodeMaturityStatus.ARCHIVED)
    )
    for response in affected_responses:
        _reset_affected_response(response, code.name)

    db.delete(code)
    db.flush()
    _refresh_after_admin_change(db, item)
    db.commit()
    return get_codebook(db, item_id)


def delete_all_codes(db: Session, item_id: str) -> AdminCodebookSummary:
    """Đặt lại codebook của một đồ vật mà không xoá raw response của nghiên cứu."""
    item = db.get(ItemModel, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")

    response_ids = list(
        db.scalars(
            select(ResponseIdea.response_id)
            .join(ResponseModel, ResponseModel.id == ResponseIdea.response_id)
            .where(ResponseModel.item_id == item_id)
            .distinct()
        ).all()
    )
    affected_responses = (
        db.scalars(select(ResponseModel).where(ResponseModel.id.in_(response_ids))).all()
        if response_ids
        else []
    )
    for response in affected_responses:
        response.mapping = _mapping_without_code(response.mapping)
        response.scoring = {}
        response.scoring_meta = {"invalidated_by": "ADMIN_CODEBOOK_RESET"}
        response.fluency = 0
        response.flexibility = 0
        response.originality = 0
        response.elaboration = 0
        response.scoring_status = ResponseScoringStatus.EXCLUDED
        response.codebook_version_id = None
        response.calibration_eligible = False
        response.scored_at = None

    version_ids = select(CodebookVersion.id).where(CodebookVersion.item_id == item_id)
    db.execute(
        update(ResponseModel)
        .where(ResponseModel.item_id == item_id)
        .values(codebook_version_id=None)
    )
    db.execute(
        delete(ResponseIdea).where(
            ResponseIdea.response_id.in_(
                select(ResponseModel.id).where(ResponseModel.item_id == item_id)
            )
        )
    )
    db.execute(delete(CodebookVersionCode).where(CodebookVersionCode.version_id.in_(version_ids)))
    db.execute(delete(CodebookVersion).where(CodebookVersion.item_id == item_id))
    db.execute(update(ItemCode).where(ItemCode.item_id == item_id).values(merged_into_id=None))
    db.execute(delete(ItemCode).where(ItemCode.item_id == item_id))

    item.active_codebook_version_id = None
    item.last_version_participant_count = 0
    item.calibration_status = ItemCalibrationStatus.COLLECTING
    db.commit()
    return get_codebook(db, item_id)
