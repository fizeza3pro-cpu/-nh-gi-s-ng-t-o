"""Nghiệp vụ codebook động và tính Originality từ dữ liệu realtime có lưu căn cứ."""

import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import (
    CodebookVersion,
    CodebookVersionCode,
    CodebookVersionStatus,
    CodeMaturityStatus,
    CodeValidationStatus,
    Item,
    ItemCalibrationStatus,
    ItemCode,
    Response,
    ResponseIdea,
    ResponseScoringStatus,
)
from app.pipeline.dynamic_mapping import normalize_code_name
from app.schemas.schemas import CuratorResult, IdeaExtractionResult, MappedIdea, MappingResult, PerIdeaScore


def list_curator_codes(db: Session, item_id: str) -> list[dict]:
    item = db.get(Item, item_id)
    if item is None:
        return []
    rows = db.scalars(
        select(ItemCode).where(
            ItemCode.item_id == item_id,
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status.in_([CodeMaturityStatus.EMERGING, CodeMaturityStatus.STABLE]),
        )
    ).all()
    return [
        {"id": row.id, "name": row.name, "description": row.description}
        for row in rows
        if _code_mentions_target(item, row)
    ]


def _mentions_target(value: str, item_name: str) -> bool:
    """So sánh không dấu để buộc output gọi đúng đồ vật mục tiêu."""
    target = normalize_code_name(item_name)
    content = normalize_code_name(value)
    return bool(target and target in content)


def _code_mentions_target(item: Item, code: ItemCode) -> bool:
    return _mentions_target(f"{code.name} {code.description}", item.name)


def _extraction_is_grounded(item: Item, idea) -> bool:
    """Ý VALID phải xác nhận đúng vật thể và nêu được vai trò của vật thể đó."""
    return bool(
        idea.uses_target_object
        and idea.target_object_role.strip()
        and _mentions_target(idea.object_used, item.name)
    )


def _curator_is_grounded(item: Item, decision, code_row: ItemCode | None = None) -> bool:
    """Curator phải xác nhận lại vật thể; code mới còn phải gọi đúng tên vật thể."""
    if not decision.target_object_confirmed or not decision.target_object_role.strip():
        return False
    if decision.decision == "CREATE_NEW":
        return _mentions_target(
            f"{decision.code_name or ''} {decision.code_description}", item.name
        )
    if decision.decision == "MATCH_EXISTING":
        return code_row is not None and _code_mentions_target(item, code_row)
    return False


def _find_or_create_code(
    db: Session,
    *,
    item_id: str,
    name: str,
    description: str,
    confidence: float,
    reason: str,
    validation_status: CodeValidationStatus,
    source_response_id: str,
) -> ItemCode:
    normalized_name = normalize_code_name(name) or f"code-{uuid.uuid4().hex[:8]}"
    existing = db.scalar(
        select(ItemCode).where(
            ItemCode.item_id == item_id,
            ItemCode.normalized_name == normalized_name,
        )
    )
    if existing:
        # Nếu AI gặp lại đúng tên của code legacy, chỉ lúc này code mới được "khám phá lại"
        # từ dữ liệu thật và tham gia codebook động; bản thân seed cũ không tự tạo tần suất.
        if existing.created_by == "LEGACY" and existing.maturity_status == CodeMaturityStatus.ARCHIVED:
            existing.created_by = "LLM_REDISCOVERED"
            existing.maturity_status = CodeMaturityStatus.EMERGING
            existing.validation_status = validation_status
            existing.description = description.strip()
            existing.source_response_id = source_response_id
            existing.admin_locked = False
            existing.confidence = confidence
            existing.relevance_reason = reason
        elif (
            existing.validation_status == CodeValidationStatus.UNCERTAIN
            and validation_status == CodeValidationStatus.ACCEPTED
            and not existing.admin_locked
        ):
            existing.validation_status = CodeValidationStatus.ACCEPTED
            existing.confidence = confidence
            existing.relevance_reason = reason
        if not existing.admin_locked and confidence > existing.confidence:
            existing.confidence = confidence
            existing.relevance_reason = reason
        return existing

    row = ItemCode(
        item_id=item_id,
        name=name.strip()[:255] or "Chưa đặt tên",
        normalized_name=normalized_name,
        description=description.strip(),
        validation_status=validation_status,
        maturity_status=CodeMaturityStatus.EMERGING,
        confidence=confidence,
        relevance_reason=reason,
        rejection_reason=reason if validation_status == CodeValidationStatus.REJECTED else "",
        source_response_id=source_response_id,
    )
    db.add(row)
    db.flush()
    return row


def persist_mapping(
    db: Session,
    *,
    item: Item,
    response: Response,
    extraction: IdeaExtractionResult,
    curator: CuratorResult,
) -> tuple[MappingResult, bool]:
    """Kiểm tra output curator, lưu code/idea và trả mapping tương thích API cũ."""
    decisions = {decision.idea_index: decision for decision in curator.decisions}
    allowed_codes = {
        row.id: row
        for row in db.scalars(select(ItemCode).where(ItemCode.item_id == item.id)).all()
    }
    mapped: list[MappedIdea] = []
    has_uncertain = False

    for index, idea in enumerate(extraction.ideas):
        status = idea.status
        code_row: ItemCode | None = None
        decision_name = "EXTRACTION"
        confidence = 1.0 if status != "VALID" else 0.0
        reason = idea.reason

        if status == "VALID" and not _extraction_is_grounded(item, idea):
            status = "INVALID"
            decision_name = "EXTRACTION_OBJECT_GUARD"
            confidence = 1.0
            reason = (
                f"Không xác nhận được vai trò của {item.name}; đồ vật được nhận diện là "
                f"{idea.object_used or 'không xác định'}."
            )

        if status == "VALID":
            decision = decisions.get(index)
            if decision is None:
                has_uncertain = True
                reason = "Code Curator không trả quyết định cho ý này."
                decision_name = "MISSING_DECISION"
            else:
                decision_name = decision.decision
                confidence = decision.confidence
                reason = decision.reason
                if decision.decision == "MATCH_EXISTING":
                    code_row = allowed_codes.get(decision.existing_code_id or "")
                    if code_row is None or code_row.maturity_status in {
                        CodeMaturityStatus.MERGED,
                        CodeMaturityStatus.ARCHIVED,
                    }:
                        has_uncertain = True
                        code_row = None
                        reason = "Curator tham chiếu code không hợp lệ hoặc đã ngừng sử dụng."
                    elif not _curator_is_grounded(item, decision, code_row):
                        status = "INVALID"
                        decision_name = "CURATOR_OBJECT_GUARD"
                        code_row = None
                        reason = f"Curator không xác nhận được vai trò của {item.name}."
                    elif confidence < settings.code_uncertain_confidence:
                        has_uncertain = True
                elif decision.decision == "CREATE_NEW":
                    grounded = _curator_is_grounded(item, decision)
                    validation = (
                        CodeValidationStatus.ACCEPTED
                        if grounded and confidence >= settings.code_accept_confidence
                        else CodeValidationStatus.UNCERTAIN
                        if grounded
                        else CodeValidationStatus.REJECTED
                    )
                    if not grounded:
                        status = "INVALID"
                        decision_name = "CURATOR_OBJECT_GUARD"
                        reason = (
                            f"Code Curator không chứng minh được code dùng đúng {item.name}."
                        )
                    has_uncertain = has_uncertain or validation == CodeValidationStatus.UNCERTAIN
                    code_row = _find_or_create_code(
                        db,
                        item_id=item.id,
                        name=decision.code_name or idea.normalized,
                        description=decision.code_description,
                        confidence=confidence,
                        reason=reason,
                        validation_status=validation,
                        source_response_id=response.id,
                    )
                    allowed_codes[code_row.id] = code_row
                else:
                    status = "INVALID"
                    code_row = _find_or_create_code(
                        db,
                        item_id=item.id,
                        name=decision.code_name or idea.normalized,
                        description=decision.code_description,
                        confidence=confidence,
                        reason=reason,
                        validation_status=CodeValidationStatus.REJECTED,
                        source_response_id=response.id,
                    )

        # Code UNCERTAIN vẫn được lưu làm bằng chứng nhưng chưa được tính điểm.
        if code_row and code_row.validation_status == CodeValidationStatus.UNCERTAIN:
            has_uncertain = True

        db.add(
            ResponseIdea(
                response_id=response.id,
                code_id=code_row.id if code_row else None,
                original=idea.original,
                normalized=idea.normalized,
                mapping_status=status,
                curator_decision=decision_name,
                confidence=confidence,
                reason=reason,
            )
        )
        mapped.append(
            MappedIdea(
                original=idea.original,
                normalized=idea.normalized,
                code=code_row.name if code_row else None,
                status=status,
                is_valid=status == "VALID" and code_row is not None,
                reason=reason,
            )
        )

    db.flush()
    return MappingResult(ideas=mapped), has_uncertain


def qualifying_participant_count(db: Session, item_id: str) -> int:
    """Đếm người có ít nhất một response đã phân loại xong và có thể đóng góp dữ liệu."""
    return int(
        db.scalar(
            select(func.count(distinct(Response.participant_id))).where(
                Response.item_id == item_id,
                Response.scoring_status.notin_(
                    [ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED]
                ),
            )
        )
        or 0
    )


def qualifying_response_count(db: Session, item_id: str) -> int:
    """Đếm mọi response đã phân loại xong, kể cả một người gửi nhiều lượt."""
    return int(
        db.scalar(
            select(func.count()).select_from(Response).where(
                Response.item_id == item_id,
                Response.scoring_status.notin_(
                    [ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED]
                ),
            )
        )
        or 0
    )


def _code_live_counts(db: Session, item_id: str) -> dict[str, tuple[int, int, int]]:
    rows = db.execute(
        select(
            ResponseIdea.code_id,
            func.count(distinct(ResponseIdea.response_id)),
            func.count(distinct(Response.participant_id)),
            func.count(ResponseIdea.id),
        )
        .join(Response, Response.id == ResponseIdea.response_id)
        .join(ItemCode, ItemCode.id == ResponseIdea.code_id)
        .where(
            Response.item_id == item_id,
            Response.scoring_status.notin_(
                [ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED]
            ),
            ResponseIdea.mapping_status == "VALID",
            or_(
                ResponseIdea.confidence >= settings.code_uncertain_confidence,
                ItemCode.admin_locked.is_(True),
            ),
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status.in_([CodeMaturityStatus.EMERGING, CodeMaturityStatus.STABLE]),
        )
        .group_by(ResponseIdea.code_id)
    ).all()
    return {code_id: (responses, participants, ideas) for code_id, responses, participants, ideas in rows}


def promote_stable_codes(db: Session, item_id: str) -> None:
    counts = _code_live_counts(db, item_id)
    for code in db.scalars(
        select(ItemCode).where(
            ItemCode.item_id == item_id,
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status == CodeMaturityStatus.EMERGING,
        )
    ).all():
        if counts.get(code.id, (0, 0, 0))[1] >= settings.code_stable_min_participants:
            code.maturity_status = CodeMaturityStatus.STABLE


def create_codebook_version(db: Session, item: Item, participant_count: int) -> CodebookVersion:
    """Đóng snapshot mới; không sửa snapshot cũ để điểm có thể tái lập."""
    previous = db.scalars(
        select(CodebookVersion).where(
            CodebookVersion.item_id == item.id,
            CodebookVersion.status == CodebookVersionStatus.ACTIVE,
        )
    ).all()
    for row in previous:
        row.status = CodebookVersionStatus.RETIRED

    max_version = db.scalar(
        select(func.max(CodebookVersion.version)).where(CodebookVersion.item_id == item.id)
    ) or 0
    response_count = db.scalar(
        select(func.count()).select_from(Response).where(
            Response.item_id == item.id,
            Response.scoring_status.notin_(
                [ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED]
            ),
        )
    ) or 0
    version = CodebookVersion(
        item_id=item.id,
        version=max_version + 1,
        participant_count=participant_count,
        response_count=response_count,
    )
    db.add(version)
    db.flush()

    counts = _code_live_counts(db, item.id)
    accepted_codes = db.scalars(
        select(ItemCode).where(
            ItemCode.item_id == item.id,
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status.in_([CodeMaturityStatus.EMERGING, CodeMaturityStatus.STABLE]),
        )
    ).all()
    # Theo Alhashim et al. (2020), "response" trong công thức là từng ý tưởng/công dụng,
    # không phải một lần submit. Vì vậy mẫu số là tổng số ý VALID đã có code được chấp nhận.
    denominator = max(sum(idea_total for _, _, idea_total in counts.values()), 1)
    for code in accepted_codes:
        response_total, participant_total, idea_total = counts.get(code.id, (0, 0, 0))
        db.add(
            CodebookVersionCode(
                version_id=version.id,
                code_id=code.id,
                response_count=response_total,
                participant_count=participant_total,
                idea_count=idea_total,
                frequency=idea_total / denominator,
            )
        )

    item.active_codebook_version_id = version.id
    item.last_version_participant_count = participant_count
    item.calibration_status = ItemCalibrationStatus.ACTIVE
    return version


def item_is_ready_for_scoring(db: Session, item: Item) -> bool:
    """Một đồ vật chỉ được chấm khi đồng thời đủ số người và số response."""
    return (
        qualifying_participant_count(db, item.id)
        >= (item.scoring_min_participants or settings.scoring_min_participants)
        and qualifying_response_count(db, item.id)
        >= (item.scoring_min_responses or settings.scoring_min_responses)
        and item.calibration_status != ItemCalibrationStatus.PAUSED
    )


def maybe_refresh_codebook(db: Session, item: Item) -> tuple[CodebookVersion | None, bool]:
    """Chỉ tạo version khi lần đầu đủ ngưỡng; response mới không làm refresh version."""
    promote_stable_codes(db, item.id)
    participant_count = qualifying_participant_count(db, item.id)
    if not item_is_ready_for_scoring(db, item):
        return None, False

    active_version = (
        db.get(CodebookVersion, item.active_codebook_version_id)
        if item.active_codebook_version_id
        else None
    )
    if active_version is None:
        item.calibration_status = ItemCalibrationStatus.CALIBRATING
        version = create_codebook_version(db, item, participant_count)
        return version, True
    return active_version, False


def originality_for_response(
    db: Session, response: Response
) -> tuple[int, int, list[str], list[PerIdeaScore], dict]:
    """Tính chỉ số bằng tần suất realtime và trả toàn bộ căn cứ để đóng băng cùng điểm."""
    valid_ideas = db.scalars(
        select(ResponseIdea)
        .join(ItemCode, ItemCode.id == ResponseIdea.code_id)
        .where(
            ResponseIdea.response_id == response.id,
            ResponseIdea.mapping_status == "VALID",
            or_(
                ResponseIdea.confidence >= settings.code_uncertain_confidence,
                ItemCode.admin_locked.is_(True),
            ),
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status.in_([CodeMaturityStatus.EMERGING, CodeMaturityStatus.STABLE]),
        )
        .order_by(ResponseIdea.created_at, ResponseIdea.id)
    ).all()
    live_counts = _code_live_counts(db, response.item_id)
    valid_idea_count = sum(idea_total for _, _, idea_total in live_counts.values())
    denominator = max(valid_idea_count, 1)

    def frequency(code_id: str) -> float:
        return live_counts.get(code_id, (0, 0, 0))[2] / denominator

    def originality(code_id: str) -> int:
        freq = frequency(code_id)
        if freq <= 0.01:
            return 2
        if freq <= 0.05:
            return 1
        return 0

    code_names = {idea.code_id: idea.code.name for idea in valid_ideas if idea.code}
    flexibility_codes = sorted(set(code_names.values()))
    frequency_rows = []
    for code_id in sorted(code_names):
        response_count, participant_count, idea_count = live_counts.get(code_id, (0, 0, 0))
        frequency_rows.append(
            {
                "code_id": code_id,
                "code_name": code_names[code_id],
                "response_count": response_count,
                "participant_count": participant_count,
                "idea_count": idea_count,
                "frequency": idea_count / denominator,
            }
        )
    basis = {
        "frequency_source": "realtime_at_scoring",
        "qualifying_participant_count": qualifying_participant_count(db, response.item_id),
        "qualifying_response_count": qualifying_response_count(db, response.item_id),
        "valid_idea_count": valid_idea_count,
        "formula": {"rare_at_or_below": 0.01, "uncommon_at_or_below": 0.05},
        "code_frequencies": frequency_rows,
    }
    per_idea = [
        PerIdeaScore(
            normalized=idea.normalized,
            code=code_names.get(idea.code_id, ""),
            originality=originality(idea.code_id),
            elaboration=1,
        )
        for idea in valid_ideas
    ]
    return len(valid_ideas), len(flexibility_codes), flexibility_codes, per_idea, basis
