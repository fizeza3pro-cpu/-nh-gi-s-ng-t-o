"""Nghiệp vụ codebook động và tính Originality từ dữ liệu realtime có lưu căn cứ."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import distinct, func, or_, select, update
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
from app.pipeline.code_retrieval import functional_key, signature_text
from app.pipeline.embedding import local_embedding
from app.pipeline.dynamic_mapping import normalize_code_name
from app.schemas.schemas import (
    CuratorResult,
    IdeaExtractionResult,
    MappedIdea,
    MappingResult,
    PerIdeaScore,
    ScoringResult,
)


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
            "embedding_model": row.embedding_model,
            "scope_history": row.scope_history or [],
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
    if decision.decision in {"CREATE_NEW", "EXPAND_EXISTING"}:
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
    embedding: list[float] | None = None,
    embedding_model: str = "",
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
        if (
            existing.maturity_status == CodeMaturityStatus.MERGED
            and existing.merged_into_id
        ):
            merged_target = db.get(ItemCode, existing.merged_into_id)
            if (
                merged_target is not None
                and merged_target.validation_status == CodeValidationStatus.ACCEPTED
                and merged_target.maturity_status == CodeMaturityStatus.ACTIVE
            ):
                return merged_target
        if not existing.functional_key and key:
            existing.functional_key = key
            existing.functional_signature = signature
            existing.inclusion_rules = inclusion_rules
            existing.exclusion_rules = exclusion_rules
            existing.positive_examples = positive_examples
            existing.embedding = embedding or local_embedding(
                f"{existing.name} {existing.description} {signature_text(signature)}"
            )
            existing.embedding_model = embedding_model or "local-hash-v1"
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
            existing.validation_status
            in {CodeValidationStatus.UNCERTAIN, CodeValidationStatus.REJECTED}
            and validation_status == CodeValidationStatus.ACCEPTED
            and not existing.admin_locked
        ):
            existing.validation_status = CodeValidationStatus.ACCEPTED
            existing.maturity_status = CodeMaturityStatus.ACTIVE
            existing.confidence = confidence
            existing.relevance_reason = reason
            existing.rejection_reason = ""
            existing.description = description.strip()
            existing.functional_key = key
            existing.functional_signature = signature
            existing.inclusion_rules = inclusion_rules
            existing.exclusion_rules = exclusion_rules
            existing.positive_examples = positive_examples
            existing.source_response_id = source_response_id
        if not existing.admin_locked and confidence > existing.confidence:
            existing.confidence = confidence
            existing.relevance_reason = reason
        if embedding:
            existing.embedding = embedding
            existing.embedding_model = embedding_model
        if not existing.admin_locked:
            existing.inclusion_rules = _unique_texts(
                existing.inclusion_rules or [], inclusion_rules
            )
            existing.exclusion_rules = _unique_texts(
                existing.exclusion_rules or [], exclusion_rules
            )
            existing.positive_examples = _unique_texts(
                existing.positive_examples or [], positive_examples
            )
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
        embedding=embedding
        or local_embedding(f"{name} {description} {signature_text(signature)}"),
        embedding_model=embedding_model or "local-hash-v1",
        scope_history=[],
    )
    db.add(row)
    db.flush()
    return row


def _all_gates_pass(decision, required: set[str]) -> bool:
    """Cổng quyết định chỉ đạt khi đủ khóa và từng giá trị đều đúng."""
    return required.issubset(decision.policy_gates) and all(
        decision.policy_gates.get(gate, False) for gate in required
    )


def _has_complete_boundaries(decision) -> bool:
    """Không tin gate tự khai nếu category thiếu biên bao gồm hoặc loại trừ."""
    def specific(rule: str, *, inclusion: bool) -> bool:
        normalized = normalize_code_name(rule)
        tokens = normalized.split()
        if len(tokens) < 4:
            return False
        if inclusion and normalized.startswith("co co che "):
            return False
        if not inclusion and normalized.startswith("khong dung de ") and len(tokens) <= 6:
            return False
        return True

    return (
        any(
            specific(rule, inclusion=True) for rule in decision.inclusion_rules
        )
        and any(
            specific(rule, inclusion=False) for rule in decision.exclusion_rules
        )
        and any(example.strip() for example in decision.positive_examples)
    )


def _relation_for_code(decision, code_id: str) -> str:
    """Đọc quan hệ cặp ý-code từ bằng chứng có cấu trúc của Curator/Challenger."""
    evaluation = next(
        (
            row
            for row in decision.existing_code_evaluations
            if str(row.get("code_id")) == code_id
        ),
        {},
    )
    return str(evaluation.get("relation") or "")


def _unique_texts(*groups: list[str]) -> list[str]:
    """Gộp bằng chứng theo thứ tự mà không nhân bản cùng một chuỗi."""
    result: list[str] = []
    seen: set[str] = set()
    for value in (item.strip() for group in groups for item in group if item.strip()):
        key = normalize_code_name(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _expand_existing_code(
    db: Session,
    *,
    item: Item,
    response: Response,
    decision,
    allowed_codes: dict[str, ItemCode],
) -> tuple[ItemCode | None, set[str], str]:
    """Mở rộng một code tại chỗ và gộp các code con đã được hai tầng xác nhận."""
    target = allowed_codes.get(decision.existing_code_id or "")
    if (
        target is None
        or target.validation_status != CodeValidationStatus.ACCEPTED
        or target.maturity_status != CodeMaturityStatus.ACTIVE
    ):
        return None, set(), "Code đích mở rộng không còn hoạt động."
    required_gates = {
        "same_functional_family",
        "broader_scope_justified",
        "previous_examples_preserved",
        "hard_negatives_excluded",
        "no_overlap_after_change",
    }
    if (
        decision.code_relation != "IDEA_BROADER_THAN_CODE"
        or not decision.reviewed_by_challenger
        or not _all_gates_pass(decision, required_gates)
        or not _has_complete_boundaries(decision)
        or _relation_for_code(decision, target.id) != "IDEA_BROADER_THAN_CODE"
    ):
        return None, set(), "Chưa đủ đồng thuận và cổng phạm vi để mở rộng code."

    absorbed: list[ItemCode] = []
    for code_id in decision.absorbed_code_ids:
        code = allowed_codes.get(code_id)
        if (
            code is None
            or code.id == target.id
            or code.validation_status != CodeValidationStatus.ACCEPTED
            or code.maturity_status != CodeMaturityStatus.ACTIVE
            or _relation_for_code(decision, code.id) != "IDEA_BROADER_THAN_CODE"
        ):
            return None, set(), "Danh sách code con cần hấp thụ chưa có đủ bằng chứng."
        absorbed.append(code)

    new_name = (decision.code_name or "").strip()[:255]
    new_description = decision.code_description.strip()
    normalized_name = normalize_code_name(new_name)
    if not new_name or not normalized_name:
        return None, set(), "Tên code mở rộng bị trống."
    duplicate = db.scalar(
        select(ItemCode).where(
            ItemCode.item_id == item.id,
            ItemCode.normalized_name == normalized_name,
            ItemCode.id != target.id,
        )
    )
    absorbed_ids = {code.id for code in absorbed}
    if duplicate is not None and duplicate.id not in absorbed_ids:
        return None, set(), "Tên code mở rộng đang chồng với một code không được hấp thụ."
    if duplicate is not None:
        duplicate.normalized_name = (
            f"{duplicate.normalized_name}-merged-{duplicate.id[:8]}"
        )[:255]
        db.flush()

    previous = {
        "name": target.name,
        "description": target.description,
        "functional_signature": target.functional_signature or {},
        "inclusion_rules": target.inclusion_rules or [],
        "exclusion_rules": target.exclusion_rules or [],
    }
    changed_code_ids = {target.id, *absorbed_ids}
    target.name = new_name
    target.normalized_name = normalized_name
    target.description = new_description
    target.functional_signature = decision.functional_signature.model_dump()
    target.functional_key = functional_key(target.functional_signature)
    target.inclusion_rules = decision.inclusion_rules
    target.exclusion_rules = decision.exclusion_rules
    target.positive_examples = _unique_texts(
        target.positive_examples or [],
        decision.positive_examples,
        *[code.positive_examples or [] for code in absorbed],
    )
    target.embedding = decision.embedding or local_embedding(
        f"{target.name} {target.description} {signature_text(target.functional_signature)}"
    )
    target.embedding_model = decision.embedding_model or "local-hash-v1"
    target.confidence = decision.confidence
    target.relevance_reason = decision.reason
    target.scope_history = [
        *(target.scope_history or []),
        {
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "source_response_id": response.id,
            "change": "AUTO_SCOPE_EXPANSION",
            "previous": previous,
            "current": {
                "name": target.name,
                "description": target.description,
                "functional_signature": target.functional_signature,
                "inclusion_rules": target.inclusion_rules,
                "exclusion_rules": target.exclusion_rules,
            },
            "absorbed_code_ids": sorted(absorbed_ids),
            "reason": decision.reason,
        },
    ]
    for code in absorbed:
        db.execute(
            update(ResponseIdea).where(ResponseIdea.code_id == code.id).values(code_id=target.id)
        )
        code.maturity_status = CodeMaturityStatus.MERGED
        code.merged_into_id = target.id
        code.relevance_reason = f"Được AI hấp thụ vào code rộng hơn: {target.name}."
    db.flush()
    return target, changed_code_ids, ""


def synchronize_response_mappings(db: Session, item_id: str) -> None:
    """Đồng bộ JSON hiển thị từ ResponseIdea sau khi code tự mở rộng hoặc gộp."""
    rows = db.scalars(select(Response).where(Response.item_id == item_id)).all()
    for row in rows:
        ideas = db.scalars(
            select(ResponseIdea)
            .where(ResponseIdea.response_id == row.id)
            .order_by(ResponseIdea.line_index, ResponseIdea.created_at, ResponseIdea.id)
        ).all()
        row.mapping = MappingResult(
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
                for idea in ideas
            ]
        ).model_dump()


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
    scope_changed = False

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
                    "code_relation": decision.code_relation,
                    "reviewed_by_challenger": decision.reviewed_by_challenger,
                    "absorbed_code_ids": decision.absorbed_code_ids,
                }
                if decision.decision == "MATCH_EXISTING":
                    code_row = allowed_codes.get(decision.existing_code_id or "")
                    relation = _relation_for_code(
                        decision, decision.existing_code_id or ""
                    )
                    if (
                        code_row is None
                        or code_row.validation_status != CodeValidationStatus.ACCEPTED
                        or code_row.maturity_status != CodeMaturityStatus.ACTIVE
                        or decision.code_relation
                        not in {"SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE"}
                        or relation not in {"SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE"}
                    ):
                        has_uncertain = True
                        code_row = None
                        reason = "Quan hệ ngữ nghĩa chưa đủ điều kiện để gắn code hiện có."
                    elif not _curator_is_grounded(item, decision, code_row):
                        has_uncertain = True
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
                    gates_pass = _all_gates_pass(decision, required_gates)
                    boundaries_complete = _has_complete_boundaries(decision)
                    core_signature_complete = all(
                        getattr(category_signature, field).strip()
                        for field in ("goal", "object_role", "mechanism")
                    )
                    if not grounded:
                        has_uncertain = True
                        decision_name = "CURATOR_OBJECT_GUARD"
                        reason = (
                            f"Code Curator không chứng minh được code dùng đúng {item.name}."
                        )
                    elif (
                        gates_pass
                        and boundaries_complete
                        and core_signature_complete
                        and decision.reviewed_by_challenger
                    ):
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
                            embedding=decision.embedding,
                            embedding_model=decision.embedding_model,
                        )
                        allowed_codes[code_row.id] = code_row
                    else:
                        has_uncertain = True
                        decision_name = "POLICY_REJECTED"
                        code_row = None
                        reason = (
                            "Category thiếu quy tắc bao gồm hoặc loại trừ cụ thể."
                            if not boundaries_complete
                            else "Chưa đủ các cổng bằng chứng bắt buộc để tạo mã mới."
                        )
                elif decision.decision == "EXPAND_EXISTING":
                    if not _curator_is_grounded(item, decision):
                        has_uncertain = True
                        decision_name = "CURATOR_OBJECT_GUARD"
                        reason = f"Chưa xác nhận được phạm vi mới sử dụng đúng {item.name}."
                    else:
                        code_row, changed_ids, expansion_error = _expand_existing_code(
                            db,
                            item=item,
                            response=response,
                            decision=decision,
                            allowed_codes=allowed_codes,
                        )
                        if code_row is None:
                            has_uncertain = True
                            decision_name = "SCOPE_REJECTED"
                            reason = expansion_error
                        else:
                            scope_changed = True
                            for changed_id in changed_ids:
                                if changed_id != code_row.id:
                                    allowed_codes.pop(changed_id, None)
                            allowed_codes[code_row.id] = code_row
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
    if scope_changed:
        synchronize_response_mappings(db, item.id)
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


def refresh_final_frequency_scores(db: Session, item_id: str) -> int:
    """Tính lại phần phụ thuộc tần suất, giữ nguyên Elaboration đã chấm bằng LLM."""
    rows = db.scalars(
        select(Response).where(
            Response.item_id == item_id,
            Response.scoring_status == ResponseScoringStatus.FINAL,
        )
    ).all()
    refreshed = 0
    refreshed_at = datetime.now(timezone.utc)
    for row in rows:
        if not row.scoring:
            continue
        previous = ScoringResult.model_validate(row.scoring)
        fluency, flexibility, codes, current_scores, basis = originality_for_response(db, row)
        previous_by_idea = {
            (score.original, score.normalized): score for score in previous.per_idea_scores
        }
        merged_scores = []
        for score in current_scores:
            old = previous_by_idea.get((score.original, score.normalized))
            merged_scores.append(
                score.model_copy(
                    update={
                        "elaboration": old.elaboration if old else 1,
                        "meaningful_word_count": old.meaningful_word_count if old else 0,
                        "elaboration_details": old.elaboration_details if old else {},
                        "note": old.note if old else "",
                    }
                )
            )
        scoring = ScoringResult(
            fluency=fluency,
            flexibility=flexibility,
            flexibility_codes=codes,
            originality=sum(score.originality for score in merged_scores),
            elaboration=sum(score.elaboration for score in merged_scores),
            per_idea_scores=merged_scores,
            summary_vi=previous.summary_vi,
        )
        row.scoring = scoring.model_dump()
        row.fluency = scoring.fluency
        row.flexibility = scoring.flexibility
        row.originality = scoring.originality
        row.elaboration = scoring.elaboration
        row.scored_at = refreshed_at
        row.scoring_meta = {
            **(row.scoring_meta or {}),
            "frequency_basis": basis,
            "frequency_refreshed_at": refreshed_at.isoformat(),
        }
        refreshed += 1
    return refreshed
