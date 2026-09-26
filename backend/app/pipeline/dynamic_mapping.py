"""Tầng mapping động: tách ý trước, sau đó dùng Code Curator để gán/tạo code."""

import json
import re
import unicodedata
from itertools import combinations
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.pipeline.code_retrieval import rank_code_candidates, signature_similarity
from app.pipeline.embedding import embed_texts
from app.pipeline.llm import LLMJSONError, chat_json
from app.pipeline.reference_dataset import reference_cases_json
from app.schemas.schemas import (
    CuratorDecision,
    CuratorResult,
    ExtractedIdea,
    IdeaExtractionResult,
    Item,
)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_EXTRACTION_TEMPLATE = (_PROMPT_DIR / "idea_extraction.txt").read_text(encoding="utf-8")
_CURATOR_TEMPLATE = (_PROMPT_DIR / "code_curator.txt").read_text(encoding="utf-8")
_CHALLENGER_TEMPLATE = (_PROMPT_DIR / "code_challenger.txt").read_text(encoding="utf-8")
_BOUNDARY_REPAIR_TEMPLATE = (_PROMPT_DIR / "code_boundary_repair.txt").read_text(
    encoding="utf-8"
)
_INVALID_VERIFIER_TEMPLATE = (_PROMPT_DIR / "idea_invalid_verifier.txt").read_text(
    encoding="utf-8"
)
_BATCH_RECONCILER_TEMPLATE = (_PROMPT_DIR / "code_batch_reconciler.txt").read_text(
    encoding="utf-8"
)

_MATCH_RELATIONS = {"SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE"}
_REVIEWABLE_DECISIONS = {
    "OUT_OF_CODEBOOK",
    "UNCERTAIN",
    "CREATE_NEW",
    "EXPAND_EXISTING",
    "INVALID",
}


def normalize_code_name(value: str) -> str:
    """Tạo khoá so sánh ổn định nhưng vẫn lưu riêng tên tiếng Việt có dấu."""
    plain = unicodedata.normalize("NFD", value.strip().lower())
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _candidate_ids(candidates: dict[int, list[dict]], idea_index: int) -> set[str]:
    """Lấy tập ID thật mà Curator được phép tham chiếu cho đúng một ý."""
    return {
        str(candidate.get("id"))
        for candidate in candidates.get(idea_index, [])
        if candidate.get("id")
    }


def _candidate_by_id(
    candidates: dict[int, list[dict]], idea_index: int, code_id: str | None
) -> dict | None:
    """Trả candidate đúng ID trong phạm vi của một ý, nếu có."""
    return next(
        (
            candidate
            for candidate in candidates.get(idea_index, [])
            if str(candidate.get("id")) == code_id
        ),
        None,
    )


def _match_review_reason(
    idea,
    decision: CuratorDecision,
    candidates: dict[int, list[dict]],
) -> str | None:
    """Từ chối MATCH mâu thuẫn với quan hệ ngữ nghĩa do Curator khai báo."""
    if decision.decision != "MATCH_EXISTING":
        return None
    candidate = _candidate_by_id(
        candidates, decision.idea_index, decision.existing_code_id
    )
    if candidate is None:
        return "existing_code_id không thuộc tập candidate hợp lệ."
    if decision.code_relation not in _MATCH_RELATIONS:
        return f"Quan hệ {decision.code_relation} không cho phép MATCH_EXISTING."
    evaluation = next(
        (
            row
            for row in decision.existing_code_evaluations
            if str(row.get("code_id")) == decision.existing_code_id
        ),
        None,
    )
    if evaluation is None:
        return "Thiếu đánh giá có cấu trúc cho code được chọn."
    evaluation_relation = str(evaluation.get("relation") or "")
    if evaluation_relation not in _MATCH_RELATIONS:
        return f"Đánh giá cặp ý-code có quan hệ {evaluation_relation or 'trống'}."
    if str(evaluation.get("verdict") or "").upper() != "MATCH":
        return "Kết luận MATCH mâu thuẫn với verdict của chính Curator."
    if str(evaluation.get("excluded_by") or "").strip():
        return "Code được chọn đồng thời vi phạm exclusion rule."
    if evaluation.get("goal_match") is not True:
        return "MATCH_EXISTING không được phép khi mục đích chức năng không khớp."
    if not any(
        evaluation.get(field) is True
        for field in ("goal_match", "role_match", "mechanism_match")
    ):
        return "Các thành phần chức năng đều không khớp nhưng Curator vẫn kết luận MATCH."
    return None


def _match_guard_evidence(
    idea,
    decision: CuratorDecision,
    candidates: dict[int, list[dict]],
) -> dict | None:
    """Lưu căn cứ backend để quyết định MATCH có thể tái kiểm toán về sau."""
    candidate = _candidate_by_id(
        candidates, decision.idea_index, decision.existing_code_id
    )
    if candidate is None:
        return None
    similarities = candidate.get("signature_similarity") or signature_similarity(
        idea.functional_signature, candidate.get("functional_signature") or {}
    )
    return {
        "source": "BACKEND_MATCH_GUARD",
        "code_id": decision.existing_code_id,
        "retrieval_score": float(candidate.get("retrieval_score") or 0.0),
        "semantic_similarity": float(candidate.get("semantic_similarity") or 0.0),
        "code_relation": decision.code_relation,
        "signature_similarity": similarities,
        "verdict": "PASS",
    }


def _normalize_curator_contract(
    curator: CuratorResult,
    ideas: IdeaExtractionResult,
    candidates: dict[int, list[dict]],
) -> CuratorResult:
    """Đưa MATCH sai hợp đồng hoặc quá yếu sang Challenger trước khi lưu."""
    normalized = []
    for decision in curator.decisions:
        allowed_ids = _candidate_ids(candidates, decision.idea_index)
        idea = (
            ideas.ideas[decision.idea_index]
            if decision.idea_index < len(ideas.ideas)
            else None
        )
        invalid_id = (
            decision.decision in {"MATCH_EXISTING", "EXPAND_EXISTING"}
            and decision.existing_code_id not in allowed_ids
        )
        review_reason = (
            _match_review_reason(idea, decision, candidates)
            if idea is not None and not invalid_id
            else None
        )
        invalid_expand_relation = (
            decision.decision == "EXPAND_EXISTING"
            and decision.code_relation != "IDEA_BROADER_THAN_CODE"
        )
        if invalid_id or review_reason or invalid_expand_relation:
            normalized.append(
                decision.model_copy(
                    update={
                        "decision": "UNCERTAIN" if invalid_expand_relation else "OUT_OF_CODEBOOK",
                        "existing_code_id": None,
                        "nearest_code_ids": sorted(allowed_ids),
                        "reason": (
                            "MATCH_EXISTING cần Challenger kiểm tra lại: "
                            + (
                                "existing_code_id không thuộc các code ứng viên hợp lệ."
                                if invalid_id
                                else (
                                    "EXPAND_EXISTING thiếu quan hệ IDEA_BROADER_THAN_CODE."
                                    if invalid_expand_relation
                                    else str(review_reason)
                                )
                            )
                        ),
                    }
                )
            )
        elif decision.decision == "MATCH_EXISTING" and idea is not None:
            audit = _match_guard_evidence(idea, decision, candidates)
            normalized.append(
                decision.model_copy(
                    update={
                        "existing_code_evaluations": [
                            *decision.existing_code_evaluations,
                            *([audit] if audit else []),
                        ]
                    }
                )
            )
        else:
            normalized.append(decision)
    return CuratorResult(decisions=normalized)


def _core_signature_complete(idea) -> bool:
    """Một category khởi tạo phải có đủ mục đích, vai trò và cơ chế."""
    return all(
        getattr(idea.functional_signature, field).strip()
        for field in ("goal", "object_role", "mechanism")
    )


def _mentions_target_object(item: Item, object_used: str) -> bool:
    """Đối chiếu tên vật thể theo tập token không dấu để sửa cờ boolean thiếu nhất quán."""
    target_tokens = set(normalize_code_name(item.name).split())
    used_tokens = set(normalize_code_name(object_used).split())
    return bool(target_tokens and target_tokens.issubset(used_tokens))


def _verify_invalid_extractions(
    *,
    item: Item,
    ideas: list[ExtractedIdea],
    client: OpenAI,
) -> tuple[list[ExtractedIdea], dict | None]:
    """Kiểm tra lần hai các câu có nghĩa bị Extraction loại quá sớm."""
    reviewable = [
        idea
        for idea in ideas
        if idea.status == "INVALID" and idea.original.strip()
    ]
    if not reviewable:
        return ideas, None

    prompt = _INVALID_VERIFIER_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        invalid_cases_json=json.dumps(
            [
                {
                    "line_index": idea.line_index,
                    "original": idea.original,
                    "normalized": idea.normalized,
                    "first_reason": idea.reason,
                }
                for idea in reviewable
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    try:
        data, meta = chat_json(
            client,
            model=settings.active_llm_model,
            temperature=settings.mapping_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.active_max_tokens,
        )
        verified = IdeaExtractionResult.model_validate(data)
    except (LLMJSONError, ValueError) as exc:
        return ideas, {"failed": True, "reason": str(exc)}

    verified_by_index = {idea.line_index: idea for idea in verified.ideas}
    final: list[ExtractedIdea] = []
    for idea in ideas:
        candidate = verified_by_index.get(idea.line_index)
        if idea.status != "INVALID" or candidate is None:
            final.append(idea)
            continue
        candidate.original = idea.original
        if (
            candidate.status == "VALID"
            and candidate.uses_target_object
            and _mentions_target_object(item, candidate.object_used)
            and candidate.target_object_role.strip()
            and _core_signature_complete(candidate)
        ):
            final.append(candidate)
        else:
            final.append(idea)
    return final, meta


def run_idea_extraction(
    item: Item,
    responses: list[str] | str,
    client: OpenAI,
    embedding_client: OpenAI | None = None,
) -> tuple[IdeaExtractionResult, dict]:
    lines = (
        [line.strip() for line in responses.splitlines() if line.strip()]
        if isinstance(responses, str)
        else [line.strip() for line in responses if line.strip()]
    )[:10]
    prompt = _EXTRACTION_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        responses_json=json.dumps(
            [{"line_index": index, "text": line} for index, line in enumerate(lines)],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        reference_cases_json=(
            reference_cases_json(
                "extraction",
                item_name=item.name,
                query_texts=lines,
                limit=settings.reference_cases_limit,
                embedding_client=embedding_client,
            )
            if settings.reference_cases_enabled
            else "[]"
        ),
    )
    data, meta = chat_json(
        client,
        model=settings.active_llm_model,
        temperature=settings.mapping_temperature,
        prompt=prompt,
        provider=settings.llm_provider,
        reasoning_effort=settings.active_reasoning_effort,
        max_tokens=settings.active_max_tokens,
    )
    result = IdeaExtractionResult.model_validate(data)
    by_line = {idea.line_index: idea for idea in result.ideas if idea.line_index < len(lines)}
    aligned = []
    contract_repairs = []
    for index, line in enumerate(lines):
        idea = by_line.get(index)
        if idea is None:
            idea = ExtractedIdea(
                line_index=index,
                original=line,
                normalized=line,
                status="INVALID",
                reason="Mô hình không trả kết quả phân tích cho dòng này.",
            )
        else:
            idea.original = line
            idea.line_index = index
            implicit_object = not idea.object_used.strip() or _mentions_target_object(
                item, idea.object_used
            )
            if (
                idea.status == "VALID"
                and not idea.uses_target_object
                and implicit_object
                and idea.target_object_role.strip()
                and _core_signature_complete(idea)
            ):
                idea.uses_target_object = True
                idea.object_used = item.name
                contract_repairs.append(
                    {
                        "idea_index": index,
                        "field": "uses_target_object",
                        "reason": "object_used, target_object_role và functional_signature xác nhận đúng vật thể.",
                    }
                )
        aligned.append(idea)
    aligned, invalid_verifier_meta = _verify_invalid_extractions(
        item=item,
        ideas=aligned,
        client=client,
    )
    result_meta = {
        **meta,
        "contract_repairs": contract_repairs,
    }
    if invalid_verifier_meta is not None:
        result_meta["invalid_verifier"] = invalid_verifier_meta
    return IdeaExtractionResult(ideas=aligned), result_meta


def run_code_curator(
    item: Item,
    ideas: IdeaExtractionResult,
    existing_codes: list[dict],
    client: OpenAI,
    embedding_client: OpenAI | None = None,
) -> tuple[CuratorResult, dict]:
    candidates = rank_code_candidates(
        ideas,
        existing_codes,
        limit=settings.code_candidate_limit,
        embedding_client=embedding_client,
    )
    valid_ideas = [
        {
            "idea_index": index,
            "normalized": idea.normalized,
            "original": idea.original,
            "object_used": idea.object_used,
            "target_object_role": idea.target_object_role,
            "functional_signature": idea.functional_signature.model_dump(),
            "nearest_codes": candidates.get(index, []),
        }
        for index, idea in enumerate(ideas.ideas)
        if idea.status == "VALID" and idea.uses_target_object
    ]
    prompt = _CURATOR_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        ideas_with_candidates_json=json.dumps(
            valid_ideas, ensure_ascii=False, separators=(",", ":")
        ),
        reference_cases_json=(
            reference_cases_json(
                "curator",
                item_name=item.name,
                query_texts=[
                    f"{idea['original']} {idea['normalized']} "
                    f"{json.dumps(idea['functional_signature'], ensure_ascii=False)}"
                    for idea in valid_ideas
                ],
                limit=settings.reference_cases_limit,
                embedding_client=embedding_client,
            )
            if settings.reference_cases_enabled
            else "[]"
        ),
    )
    meta: dict = {}
    try:
        data, meta = chat_json(
            client,
            model=settings.active_curator_model,
            temperature=settings.code_curator_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.active_max_tokens,
        )
        result = _normalize_curator_contract(
            CuratorResult.model_validate(data), ideas, candidates
        )
    except (LLMJSONError, ValueError) as exc:
        # Controller sẽ thử Curator lần nữa; nếu vẫn lỗi, từng ý được giữ để đối chiếu sau.
        return CuratorResult(decisions=[]), {
            "adjudicator": {**meta, "failed": True, "reason": str(exc)},
            "challenger": {"skipped": True, "reason": "invalid_curator_output"},
            "batch_reconciliation": {"skipped": True, "reason": "invalid_curator_output"},
        }
    result, challenge_meta = run_code_challenger(
        item, ideas, candidates, result, client, embedding_client
    )
    result, reconciliation_meta = _reconcile_new_code_batch(
        item=item,
        ideas=ideas,
        curator=result,
        client=client,
    )
    result = _attach_decision_embeddings(result, embedding_client)
    return result, {
        "adjudicator": meta,
        "challenger": challenge_meta,
        "batch_reconciliation": reconciliation_meta,
    }


def _attach_decision_embeddings(
    curator: CuratorResult, embedding_client: OpenAI | None
) -> CuratorResult:
    """Gắn vector do backend sinh; không tin vector hoặc model name từ LLM."""
    selected = [
        decision
        for decision in curator.decisions
        if decision.decision in {"CREATE_NEW", "EXPAND_EXISTING"}
    ]
    if not selected:
        return curator
    texts = [
        f"{decision.code_name or ''} {decision.code_description} "
        f"{json.dumps(decision.functional_signature.model_dump(), ensure_ascii=False)}"
        for decision in selected
    ]
    batch = embed_texts(texts, embedding_client)
    vectors = iter(batch.vectors)
    selected_ids = {decision.idea_index for decision in selected}
    decisions = []
    for decision in curator.decisions:
        if decision.idea_index in selected_ids and decision.decision in {
            "CREATE_NEW",
            "EXPAND_EXISTING",
        }:
            decisions.append(
                decision.model_copy(
                    update={
                        "embedding": next(vectors),
                        "embedding_model": batch.model,
                    }
                )
            )
        else:
            decisions.append(decision)
    return CuratorResult(decisions=decisions)


def _has_complete_boundaries(decision: CuratorDecision) -> bool:
    """Code mới hoặc code mở rộng phải có cả biên bao gồm và biên loại trừ."""
    return (
        any(rule.strip() for rule in decision.inclusion_rules)
        and any(rule.strip() for rule in decision.exclusion_rules)
        and any(example.strip() for example in decision.positive_examples)
    )


def _boundary_rule_is_specific(rule: str, *, inclusion: bool) -> bool:
    """Loại các câu mẫu hình thức không mô tả được ranh giới chức năng."""
    normalized = normalize_code_name(rule)
    tokens = normalized.split()
    if len(tokens) < 4:
        return False
    if inclusion and normalized.startswith("co co che "):
        return False
    if not inclusion and normalized.startswith("khong dung de ") and len(tokens) <= 6:
        return False
    return True


def _has_specific_boundaries(decision: CuratorDecision) -> bool:
    """Ranh giới phải có nội dung cụ thể, không chỉ là câu khẳng định hình thức."""
    return (
        _has_complete_boundaries(decision)
        and any(
            _boundary_rule_is_specific(rule, inclusion=True)
            for rule in decision.inclusion_rules
        )
        and any(
            _boundary_rule_is_specific(rule, inclusion=False)
            for rule in decision.exclusion_rules
        )
    )


def _repair_missing_boundaries(
    *,
    item: Item,
    cases: list[dict],
    challenged: CuratorResult,
    client: OpenAI,
) -> tuple[CuratorResult, dict | None]:
    """Gọi lại bằng prompt ngắn khi Challenger quên mô tả ranh giới category."""
    incomplete = [
        decision
        for decision in challenged.decisions
        if decision.decision in {"CREATE_NEW", "EXPAND_EXISTING"}
        and not _has_specific_boundaries(decision)
    ]
    if not incomplete:
        return challenged, None

    cases_by_index = {int(case["idea_index"]): case for case in cases}
    repair_cases = []
    for decision in incomplete:
        case = cases_by_index.get(decision.idea_index, {})
        repair_cases.append(
            {
                "idea_index": decision.idea_index,
                "original": case.get("original", ""),
                "normalized": case.get("normalized", ""),
                "decision_to_preserve": decision.model_dump(
                    exclude={"embedding", "embedding_model"}
                ),
                "nearest_codes": case.get("nearest_codes", []),
                "other_ideas_in_submission": [
                    {
                        "idea_index": other.get("idea_index"),
                        "original": other.get("original", ""),
                        "functional_signature": other.get("functional_signature", {}),
                    }
                    for other in cases
                    if other.get("idea_index") != decision.idea_index
                ],
            }
        )

    prompt = _BOUNDARY_REPAIR_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        repair_cases_json=json.dumps(
            repair_cases, ensure_ascii=False, separators=(",", ":")
        ),
    )
    try:
        data, meta = chat_json(
            client,
            model=settings.active_curator_model,
            temperature=settings.code_curator_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.active_max_tokens,
        )
        repaired = CuratorResult.model_validate(data)
    except (LLMJSONError, ValueError) as exc:
        # Thiếu ranh giới thì không được tạo/mở rộng code.
        repaired = CuratorResult(decisions=[])
        meta = {"failed": True, "reason": str(exc)}
    repaired_by_index = {
        decision.idea_index: decision for decision in repaired.decisions
    }
    incomplete_indices = {decision.idea_index for decision in incomplete}
    final: list[CuratorDecision] = []
    for decision in challenged.decisions:
        if decision.idea_index not in incomplete_indices:
            final.append(decision)
            continue
        candidate = repaired_by_index.get(decision.idea_index)
        same_target = (
            decision.decision != "EXPAND_EXISTING"
            or (
                candidate is not None
                and candidate.existing_code_id == decision.existing_code_id
                and candidate.code_relation == "IDEA_BROADER_THAN_CODE"
            )
        )
        if (
            candidate is not None
            and candidate.decision == decision.decision
            and same_target
            and _has_specific_boundaries(candidate)
        ):
            final.append(candidate)
            continue

        failed_gate = (
            "counterexample_passed"
            if decision.decision == "CREATE_NEW"
            else "hard_negatives_excluded"
        )
        final.append(
            decision.model_copy(
                update={
                    "decision": "UNCERTAIN",
                    "code_relation": "UNCERTAIN",
                    "existing_code_id": None,
                    "policy_gates": {
                        **decision.policy_gates,
                        failed_gate: False,
                    },
                    "reason": (
                        "Chưa xác lập được đồng thời quy tắc bao gồm và loại trừ "
                        "cho phạm vi category."
                    ),
                }
            )
        )
    return CuratorResult(decisions=final), meta


def _potential_new_code_overlaps(
    decisions: list[CuratorDecision],
) -> list[dict]:
    """Tìm cặp cần phân xử chung; điểm chỉ kích hoạt kiểm tra, không tự quyết định gộp."""
    overlaps = []
    for left, right in combinations(decisions, 2):
        similarities = signature_similarity(
            left.functional_signature, right.functional_signature
        )
        if (
            similarities["weighted"] >= 0.65
            and similarities["object_role"] >= 0.5
            and similarities["mechanism"] >= 0.5
        ):
            overlaps.append(
                {
                    "left_idea_index": left.idea_index,
                    "right_idea_index": right.idea_index,
                    "signature_similarity": similarities,
                }
            )
    return overlaps


def _reconcile_new_code_batch(
    *,
    item: Item,
    ideas: IdeaExtractionResult,
    curator: CuratorResult,
    client: OpenAI,
) -> tuple[CuratorResult, dict]:
    """Ngăn nhiều ý cùng lượt tạo các category chồng lấn trước khi ghi database."""
    proposed = [
        decision for decision in curator.decisions if decision.decision == "CREATE_NEW"
    ]
    overlaps = _potential_new_code_overlaps(proposed)
    if len(proposed) < 2 or not overlaps:
        return curator, {"skipped": True, "reason": "no_potential_overlap"}

    prompt = _BATCH_RECONCILER_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        proposals_json=json.dumps(
            [
                {
                    "idea_index": decision.idea_index,
                    "original": ideas.ideas[decision.idea_index].original,
                    "normalized": ideas.ideas[decision.idea_index].normalized,
                    "proposed_decision": decision.model_dump(
                        exclude={"embedding", "embedding_model"}
                    ),
                }
                for decision in proposed
                if decision.idea_index < len(ideas.ideas)
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        overlap_pairs_json=json.dumps(
            overlaps, ensure_ascii=False, separators=(",", ":")
        ),
    )
    try:
        data, meta = chat_json(
            client,
            model=settings.active_curator_model,
            temperature=settings.code_curator_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.active_max_tokens,
        )
        reconciled = CuratorResult.model_validate(data)
    except (LLMJSONError, ValueError) as exc:
        overlap_indices = {
            int(pair[key])
            for pair in overlaps
            for key in ("left_idea_index", "right_idea_index")
        }
        final = [
            decision.model_copy(
                update={
                    "decision": "UNCERTAIN",
                    "code_relation": "UNCERTAIN",
                    "reason": "Không hoàn tất được bước kiểm tra chồng lấn code trong cùng lượt.",
                }
            )
            if decision.idea_index in overlap_indices
            else decision
            for decision in curator.decisions
        ]
        return CuratorResult(decisions=final), {
            "failed": True,
            "reason": str(exc),
            "overlap_pairs": overlaps,
        }

    original_by_index = {decision.idea_index: decision for decision in proposed}
    candidate_by_index = {
        decision.idea_index: decision for decision in reconciled.decisions
    }
    accepted: dict[int, CuratorDecision] = {}
    for idea_index, original in original_by_index.items():
        candidate = candidate_by_index.get(idea_index)
        if (
            candidate is not None
            and candidate.decision == "CREATE_NEW"
            and candidate.code_name
            and candidate.target_object_confirmed
            and candidate.target_object_role.strip()
            and _has_specific_boundaries(candidate)
            and all(
                getattr(candidate.functional_signature, field).strip()
                for field in ("goal", "object_role", "mechanism")
            )
        ):
            accepted[idea_index] = candidate.model_copy(
                update={"reviewed_by_challenger": True}
            )
        else:
            accepted[idea_index] = original.model_copy(
                update={
                    "decision": "UNCERTAIN",
                    "code_relation": "UNCERTAIN",
                    "reason": "Batch Reconciler không trả category có ranh giới hợp lệ.",
                }
            )

    # Các ý được Reconciler xếp cùng category phải dùng đúng một bộ định nghĩa và ví dụ hợp nhất.
    groups: dict[str, list[CuratorDecision]] = {}
    for decision in accepted.values():
        if decision.decision == "CREATE_NEW":
            groups.setdefault(normalize_code_name(decision.code_name or ""), []).append(
                decision
            )
    for group in groups.values():
        if len(group) < 2:
            continue
        canonical = group[0]
        examples = list(
            dict.fromkeys(
                example.strip()
                for decision in group
                for example in decision.positive_examples
                if example.strip()
            )
        )
        for decision in group:
            accepted[decision.idea_index] = decision.model_copy(
                update={
                    "code_name": canonical.code_name,
                    "code_description": canonical.code_description,
                    "functional_signature": canonical.functional_signature,
                    "inclusion_rules": canonical.inclusion_rules,
                    "exclusion_rules": canonical.exclusion_rules,
                    "positive_examples": examples,
                }
            )

    # Nếu cặp nghi chồng lấn vẫn thành hai tên khác nhau, không ghi cả hai vào codebook.
    unresolved_indices: set[int] = set()
    for pair in overlaps:
        left_index = int(pair["left_idea_index"])
        right_index = int(pair["right_idea_index"])
        left = accepted.get(left_index)
        right = accepted.get(right_index)
        if (
            left is not None
            and right is not None
            and left.decision == "CREATE_NEW"
            and right.decision == "CREATE_NEW"
            and normalize_code_name(left.code_name or "")
            != normalize_code_name(right.code_name or "")
        ):
            unresolved_indices.update({left_index, right_index})
    for idea_index in unresolved_indices:
        accepted[idea_index] = accepted[idea_index].model_copy(
            update={
                "decision": "UNCERTAIN",
                "code_relation": "UNCERTAIN",
                "reason": (
                    "Các đề xuất code trong cùng lượt còn chồng lấn nhưng chưa thống nhất "
                    "được một category chung."
                ),
            }
        )

    final = [
        accepted.get(decision.idea_index, decision) for decision in curator.decisions
    ]
    return CuratorResult(decisions=final), {
        **meta,
        "overlap_pairs": overlaps,
        "unresolved_idea_indices": sorted(unresolved_indices),
    }


def run_code_challenger(
    item: Item,
    ideas: IdeaExtractionResult,
    candidates: dict[int, list[dict]],
    curator: CuratorResult,
    client: OpenAI,
    embedding_client: OpenAI | None = None,
) -> tuple[CuratorResult, dict]:
    """Phản biện code mới, mở rộng phạm vi và mọi quyết định chưa chắc chắn."""
    reviewable = [
        decision
        for decision in curator.decisions
        if decision.decision in _REVIEWABLE_DECISIONS
    ]
    if not reviewable:
        return curator, {"skipped": True, "reason": "no_reviewable_decision"}

    cases = []
    for decision in reviewable:
        if decision.idea_index >= len(ideas.ideas):
            continue
        idea = ideas.ideas[decision.idea_index]
        cases.append(
            {
                "idea_index": decision.idea_index,
                "original": idea.original,
                "normalized": idea.normalized,
                "functional_signature": idea.functional_signature.model_dump(),
                "adjudicator_reason": decision.reason,
                "adjudicator_decision": decision.decision,
                "adjudicator_relation": decision.code_relation,
                "proposed_code": {
                    "existing_code_id": decision.existing_code_id,
                    "name": decision.code_name,
                    "description": decision.code_description,
                    "inclusion_rules": decision.inclusion_rules,
                    "exclusion_rules": decision.exclusion_rules,
                    "absorbed_code_ids": decision.absorbed_code_ids,
                },
                "nearest_codes": candidates.get(decision.idea_index, []),
            }
        )
    if not cases:
        return curator, {"skipped": True, "reason": "invalid_indices"}

    prompt = _CHALLENGER_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        codebook_is_empty=str(not any(candidates.values())).lower(),
        challenger_cases_json=json.dumps(
            cases, ensure_ascii=False, separators=(",", ":")
        ),
        reference_cases_json=(
            reference_cases_json(
                "challenger",
                item_name=item.name,
                query_texts=[
                    f"{case['original']} {case['normalized']} "
                    f"{json.dumps(case['functional_signature'], ensure_ascii=False)}"
                    for case in cases
                ],
                limit=settings.reference_cases_limit,
                embedding_client=embedding_client,
            )
            if settings.reference_cases_enabled
            else "[]"
        ),
    )
    meta: dict = {}
    try:
        data, meta = chat_json(
            client,
            model=settings.active_curator_model,
            temperature=settings.code_curator_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.active_max_tokens,
        )
        challenged = CuratorResult.model_validate(data)
    except (LLMJSONError, ValueError) as exc:
        # Không chấp nhận quyết định chưa được Challenger phản biện.
        return CuratorResult(
            decisions=[
                decision.model_copy(
                    update={
                        "decision": "UNCERTAIN",
                        "code_relation": "UNCERTAIN",
                        "existing_code_id": None,
                        "reason": "Challenger không trả quyết định hợp lệ; cần đối chiếu lại.",
                    }
                )
                if decision.decision in _REVIEWABLE_DECISIONS
                else decision
                for decision in curator.decisions
            ]
        ), {**meta, "failed": True, "reason": str(exc)}
    challenged, boundary_repair_meta = _repair_missing_boundaries(
        item=item,
        cases=cases,
        challenged=challenged,
        client=client,
    )
    if boundary_repair_meta is not None:
        meta = {**meta, "boundary_repair": boundary_repair_meta}
    replacements = {decision.idea_index: decision for decision in challenged.decisions}
    source_by_index = {decision.idea_index: decision for decision in reviewable}
    for idea_index, source in source_by_index.items():
        replacement = replacements.get(idea_index)
        if replacement is None:
            replacements[idea_index] = source.model_copy(
                update={
                    "decision": "UNCERTAIN",
                    "existing_code_id": None,
                    "reason": "Challenger không trả quyết định cho trường hợp cần phản biện.",
                }
            )
            continue
        allowed_ids = _candidate_ids(candidates, idea_index)
        invalid_match = (
            replacement.decision in {"MATCH_EXISTING", "EXPAND_EXISTING"}
            and replacement.existing_code_id not in allowed_ids
        )
        idea = ideas.ideas[idea_index] if idea_index < len(ideas.ideas) else None
        weak_match_reason = (
            _match_review_reason(idea, replacement, candidates)
            if idea is not None and not invalid_match
            else None
        )
        invalid_expand = (
            replacement.decision == "EXPAND_EXISTING"
            and (
                source.decision != "EXPAND_EXISTING"
                or source.existing_code_id != replacement.existing_code_id
                or replacement.code_relation != "IDEA_BROADER_THAN_CODE"
            )
        )
        create_without_agreement = (
            replacement.decision == "CREATE_NEW"
            and source.decision not in {"OUT_OF_CODEBOOK", "CREATE_NEW"}
        )
        if invalid_match or weak_match_reason or invalid_expand or create_without_agreement:
            replacements[idea_index] = replacement.model_copy(
                update={
                    "decision": "UNCERTAIN",
                    "existing_code_id": None,
                    "reason": (
                        "Challenger chưa chứng minh được MATCH an toàn: "
                        + (
                            "code không thuộc tập ứng viên hợp lệ."
                            if invalid_match
                            else (
                                "hai tầng không đồng ý về việc mở rộng/tạo code."
                                if invalid_expand or create_without_agreement
                                else str(weak_match_reason)
                            )
                        )
                    ),
                }
            )
        elif replacement.decision == "MATCH_EXISTING" and idea is not None:
            audit = _match_guard_evidence(idea, replacement, candidates)
            replacements[idea_index] = replacement.model_copy(
                update={
                    "existing_code_evaluations": [
                        *replacement.existing_code_evaluations,
                        *([audit] if audit else []),
                    ],
                    "reviewed_by_challenger": True,
                }
            )
        elif replacement.decision in {"CREATE_NEW", "EXPAND_EXISTING"}:
            replacements[idea_index] = replacement.model_copy(
                update={"reviewed_by_challenger": True}
            )
        elif replacement.decision == "INVALID":
            replacements[idea_index] = replacement.model_copy(
                update=(
                    {"reviewed_by_challenger": True}
                    if source.decision == "INVALID"
                    else {
                        "decision": "UNCERTAIN",
                        "reason": "Curator và Challenger bất đồng về tính hợp lệ của ý.",
                    }
                )
            )
    final = [
        replacements.get(decision.idea_index, decision)
        if decision.decision in _REVIEWABLE_DECISIONS
        else decision
        for decision in curator.decisions
    ]
    return CuratorResult(decisions=final), meta
