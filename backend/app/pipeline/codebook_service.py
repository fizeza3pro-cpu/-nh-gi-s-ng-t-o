"""Nghiệp vụ codebook động và tính Originality từ dữ liệu realtime có lưu căn cứ."""

import uuid

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import (
    CodeMaturityStatus,
    CodeValidationStatus,
    Item,
    ItemCalibrationStatus,
    ItemCode,
    Response,
    ResponseIdea,
    ResponseScoringStatus,
)
from app.pipeline.code_retrieval import functional_key, local_embedding, signature_text
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
            ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
        )
    ).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "functional_key": row.functional_key,
            "functional_signature": row.functional_signature or {},
            "inclusion_rules": row.inclusion_rules or [],
            "exclusion_rules": row.exclusion_rules or [],
            "positive_examples": row.positive_examples or [],
            "embedding": row.embedding or [],
        }
        for row in rows
        if _code_mentions_target(item, row)
    ]


def _mentions_target(value: str, item_name: str) -> bool:
    """So sánh không dấu để buộc output gọi đúng đồ vật mục tiêu."""
    target_tokens = set(normalize_code_name(item_name).split())
    content_tokens = set(normalize_code_name(value).split())
    return bool(target_tokens and target_tokens.issubset(content_tokens))


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
    signature: dict,
    inclusion_rules: list[str],
    exclusion_rules: list[str],
    positive_examples: list[str],
) -> ItemCode:
    normalized_name = normalize_code_name(name) or f"code-{uuid.uuid4().hex[:8]}"
    key = functional_key(signature)
    existing = db.scalar(
        select(ItemCode).where(
            ItemCode.item_id == item_id,
            or_(
                ItemCode.normalized_name == normalized_name,
                ItemCode.functional_key == key if key else ItemCode.normalized_name == normalized_name,
            ),
        ).with_for_update()
    )
    if existing:
        if not existing.functional_key and key:
            existing.functional_key = key
            existing.functional_signature = signature
            existing.inclusion_rules = inclusion_rules
            existing.exclusion_rules = exclusion_rules
            existing.positive_examples = positive_examples
            existing.embedding = local_embedding(
                f"{existing.name} {existing.description} {signature_text(signature)}"
            )
        # Nếu AI gặp lại đúng tên của code legacy, chỉ lúc này code mới được "khám phá lại"
        # từ dữ liệu thật và tham gia codebook động; bản thân seed cũ không tự tạo tần suất.
        if (
            existing.created_by == "LEGACY"
            and existing.validation_status == CodeValidationStatus.REJECTED
        ):
            existing.created_by = "LLM_REDISCOVERED"
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
        maturity_status=CodeMaturityStatus.ACTIVE,
        confidence=confidence,
        relevance_reason=reason,
        rejection_reason=reason if validation_status == CodeValidationStatus.REJECTED else "",
        source_response_id=source_response_id,
        functional_key=key,
        functional_signature=signature,
        inclusion_rules=inclusion_rules,
        exclusion_rules=exclusion_rules,
        positive_examples=positive_examples,
        embedding=local_embedding(f"{name} {description} {signature_text(signature)}"),
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
        idea_signature = idea.functional_signature
        evidence: dict = {"idea_functional_signature": idea_signature.model_dump()}

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
                category_signature = (
                    decision.functional_signature
                    if decision.functional_signature.goal
                    else idea_signature
                )
                evidence = {
                    "idea_functional_signature": idea_signature.model_dump(),
                    "curator_functional_signature": decision.functional_signature.model_dump(),
                    "existing_code_evaluations": decision.existing_code_evaluations,
                    "nearest_code_ids": decision.nearest_code_ids,
                    "policy_gates": decision.policy_gates,
                    "challenge_reason": decision.challenge_reason,
                }
                if decision.decision == "MATCH_EXISTING":
                    code_row = allowed_codes.get(decision.existing_code_id or "")
                    if code_row is None or code_row.maturity_status != CodeMaturityStatus.ACTIVE:
                        has_uncertain = True
                        code_row = None
                        reason = "Curator tham chiếu code không hợp lệ hoặc đã ngừng sử dụng."
                    elif not _curator_is_grounded(item, decision, code_row):
                        status = "INVALID"
                        decision_name = "CURATOR_OBJECT_GUARD"
                        code_row = None
                        reason = f"Curator không xác nhận được vai trò của {item.name}."
                elif decision.decision == "CREATE_NEW":
                    grounded = _curator_is_grounded(item, decision)
                    required_gates = {
                        "response_is_valid",
                        "no_existing_code_covers",
                        "functionally_distinct",
                        "granularity_consistent",
                        "paraphrase_stable",
                        "counterexample_passed",
                    }
                    gates_pass = required_gates.issubset(decision.policy_gates) and all(
                        decision.policy_gates.get(gate, False) for gate in required_gates
                    )
                    core_signature_complete = all(
                        getattr(category_signature, field).strip()
                        for field in ("goal", "object_role", "mechanism")
                    )
                    if not grounded:
                        status = "INVALID"
                        decision_name = "CURATOR_OBJECT_GUARD"
                        reason = (
                            f"Code Curator không chứng minh được code dùng đúng {item.name}."
                        )
                    elif gates_pass and core_signature_complete:
                        code_row = _find_or_create_code(
                            db,
                            item_id=item.id,
                            name=decision.code_name or idea.normalized,
                            description=decision.code_description,
                            confidence=confidence,
                            reason=reason,
                            validation_status=CodeValidationStatus.ACCEPTED,
                            source_response_id=response.id,
                            signature=category_signature.model_dump(),
                            inclusion_rules=decision.inclusion_rules,
                            exclusion_rules=decision.exclusion_rules,
                            positive_examples=decision.positive_examples,
                        )
                        allowed_codes[code_row.id] = code_row
                    else:
                        has_uncertain = True
                        decision_name = "POLICY_REJECTED"
                        code_row = None
                        reason = "Chưa đủ các cổng bằng chứng bắt buộc để tạo mã mới."
                elif decision.decision in {"OUT_OF_CODEBOOK", "UNCERTAIN"}:
                    has_uncertain = True
                    code_row = None
                else:
                    status = "INVALID"

        db.add(
            ResponseIdea(
                response_id=response.id,
                code_id=code_row.id if code_row else None,
                original=idea.original,
                normalized=idea.normalized,
                line_index=idea.line_index,
                functional_signature=idea_signature.model_dump(),
                mapping_evidence=evidence,
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
                line_index=idea.line_index,
                functional_signature=idea_signature,
                curator_decision=decision_name,
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


def qualifying_idea_count(db: Session, item_id: str) -> int:
    """Đếm ý VALID đã gắn mã được chấp nhận của một đồ vật."""
    return int(
        db.scalar(
            select(func.count(ResponseIdea.id))
            .join(Response, Response.id == ResponseIdea.response_id)
            .join(ItemCode, ItemCode.id == ResponseIdea.code_id)
            .where(
                Response.item_id == item_id,
                Response.scoring_status.notin_(
                    [ResponseScoringStatus.PENDING_REVIEW, ResponseScoringStatus.EXCLUDED]
                ),
                ResponseIdea.mapping_status == "VALID",
                ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
                ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
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
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
        )
        .group_by(ResponseIdea.code_id)
    ).all()
    return {code_id: (responses, participants, ideas) for code_id, responses, participants, ideas in rows}


def item_is_ready_for_scoring(db: Session, item: Item) -> bool:
    """Chỉ chấm khi đủ đồng thời số người và số ý hợp lệ theo thiết kế nghiên cứu."""
    return (
        item.calibration_status != ItemCalibrationStatus.PAUSED
        and qualifying_participant_count(db, item.id)
        >= (item.scoring_min_participants or settings.scoring_min_participants)
        and qualifying_idea_count(db, item.id)
        >= (item.scoring_min_ideas or settings.scoring_min_ideas)
    )


def refresh_item_scoring_state(db: Session, item: Item) -> bool:
    """Đồng bộ trạng thái thu thập và báo thời điểm đồ vật vừa đủ ngưỡng."""
    was_active = item.calibration_status == ItemCalibrationStatus.ACTIVE
    ready = item_is_ready_for_scoring(db, item)
    if item.calibration_status != ItemCalibrationStatus.PAUSED:
        item.calibration_status = (
            ItemCalibrationStatus.ACTIVE if ready else ItemCalibrationStatus.COLLECTING
        )
    return ready and not was_active


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
            ItemCode.validation_status == CodeValidationStatus.ACCEPTED,
            ItemCode.maturity_status == CodeMaturityStatus.ACTIVE,
        )
        .order_by(ResponseIdea.created_at, ResponseIdea.id)
    ).all()
    fluency = int(
        db.scalar(
            select(func.count()).select_from(ResponseIdea).where(
                ResponseIdea.response_id == response.id,
                ResponseIdea.mapping_status == "VALID",
            )
        )
        or 0
    )
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
        "qualifying_idea_count": qualifying_idea_count(db, response.item_id),
        "valid_idea_count": valid_idea_count,
        "formula": {"rare_at_or_below": 0.01, "uncommon_at_or_below": 0.05},
        "code_frequencies": frequency_rows,
    }
    per_idea = [
        PerIdeaScore(
            original=idea.original,
            normalized=idea.normalized,
            code=code_names.get(idea.code_id, ""),
            originality=originality(idea.code_id),
            elaboration=1,
        )
        for idea in valid_ideas
    ]
    return fluency, len(flexibility_codes), flexibility_codes, per_idea, basis
