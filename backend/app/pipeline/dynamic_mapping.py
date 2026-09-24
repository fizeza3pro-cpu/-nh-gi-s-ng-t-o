"""Tầng mapping động: tách ý trước, sau đó dùng Code Curator để gán/tạo code."""

import json
import re
import unicodedata
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.pipeline.code_retrieval import rank_code_candidates, signature_similarity
from app.pipeline.llm import chat_json
from app.pipeline.reference_dataset import reference_cases_json
from app.schemas.schemas import CuratorDecision, CuratorResult, IdeaExtractionResult, Item

_PROMPT_DIR = Path(__file__).parent / "prompts"
_EXTRACTION_TEMPLATE = (_PROMPT_DIR / "idea_extraction.txt").read_text(encoding="utf-8")
_CURATOR_TEMPLATE = (_PROMPT_DIR / "code_curator.txt").read_text(encoding="utf-8")
_CHALLENGER_TEMPLATE = (_PROMPT_DIR / "code_challenger.txt").read_text(encoding="utf-8")


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
    """Phát hiện MATCH yếu để buộc một lượt phản biện thay vì tin top-1 retrieval."""
    if decision.decision != "MATCH_EXISTING":
        return None
    candidate = _candidate_by_id(
        candidates, decision.idea_index, decision.existing_code_id
    )
    if candidate is None:
        return "existing_code_id không thuộc tập candidate hợp lệ."
    similarities = candidate.get("signature_similarity") or signature_similarity(
        idea.functional_signature, candidate.get("functional_signature") or {}
    )
    retrieval_score = float(candidate.get("retrieval_score") or 0.0)
    if retrieval_score < settings.code_match_review_threshold:
        return (
            f"retrieval_score={retrieval_score:.6f} thấp hơn ngưỡng phản biện "
            f"{settings.code_match_review_threshold:.6f}."
        )
    if not any(
        float(similarities.get(field) or 0.0) > 0
        for field in ("goal", "object_role", "mechanism")
    ):
        return "Không có bằng chứng từ vựng ở goal, object_role hoặc mechanism."
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
        "review_threshold": settings.code_match_review_threshold,
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
            decision.decision == "MATCH_EXISTING"
            and decision.existing_code_id not in allowed_ids
        )
        review_reason = (
            _match_review_reason(idea, decision, candidates)
            if idea is not None and not invalid_id
            else None
        )
        if invalid_id or review_reason:
            normalized.append(
                decision.model_copy(
                    update={
                        "decision": "OUT_OF_CODEBOOK",
                        "existing_code_id": None,
                        "nearest_code_ids": sorted(allowed_ids),
                        "reason": (
                            "MATCH_EXISTING cần Challenger kiểm tra lại: "
                            + (
                                "existing_code_id không thuộc các code ứng viên hợp lệ."
                                if invalid_id
                                else str(review_reason)
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


def _bootstrap_new_code(item: Item, idea, prior: CuratorDecision) -> CuratorDecision:
    """Tạo code đầu tiên từ chữ ký chức năng, không phụ thuộc cách diễn đạt bề mặt."""
    signature = idea.functional_signature
    code_name = idea.normalized.strip() or signature.goal.strip()
    description = (
        f"Dùng {item.name} như {signature.object_role} để {signature.goal} "
        f"thông qua {signature.mechanism}."
    )
    required_gates = {
        "response_is_valid": True,
        "no_existing_code_covers": True,
        "functionally_distinct": True,
        "granularity_consistent": True,
        "paraphrase_stable": True,
        "counterexample_passed": True,
    }
    return CuratorDecision(
        idea_index=prior.idea_index,
        decision="CREATE_NEW",
        existing_code_id=None,
        code_name=code_name[:255],
        code_description=description,
        target_object_confirmed=True,
        target_object_role=idea.target_object_role or signature.object_role,
        functional_signature=signature,
        inclusion_rules=[
            f"Mục đích cốt lõi: {signature.goal}",
            f"Vai trò của {item.name}: {signature.object_role}",
            f"Cơ chế chính: {signature.mechanism}",
        ],
        exclusion_rules=[
            "Không bao gồm ý có mục đích, vai trò hoặc cơ chế cốt lõi khác."
        ],
        positive_examples=[idea.original],
        nearest_code_ids=[],
        policy_gates=required_gates,
        confidence=max(prior.confidence, 0.75),
        reason="Khởi tạo codebook từ một ý hợp lệ có đủ chữ ký chức năng.",
        challenge_reason=(
            "Không có code ứng viên để khớp; category được chuẩn hoá từ "
            "goal, object_role và mechanism."
        ),
    )


def run_idea_extraction(
    item: Item, responses: list[str] | str, client: OpenAI
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
            from app.schemas.schemas import ExtractedIdea

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
            if (
                idea.status == "VALID"
                and not idea.uses_target_object
                and _mentions_target_object(item, idea.object_used)
                and idea.target_object_role.strip()
                and _core_signature_complete(idea)
            ):
                idea.uses_target_object = True
                contract_repairs.append(
                    {
                        "idea_index": index,
                        "field": "uses_target_object",
                        "reason": "object_used, target_object_role và functional_signature xác nhận đúng vật thể.",
                    }
                )
        aligned.append(idea)
    return IdeaExtractionResult(ideas=aligned), {
        **meta,
        "contract_repairs": contract_repairs,
    }


def run_code_curator(
    item: Item,
    ideas: IdeaExtractionResult,
    existing_codes: list[dict],
    client: OpenAI,
) -> tuple[CuratorResult, dict]:
    candidates = rank_code_candidates(ideas, existing_codes, limit=5)
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
            )
            if settings.reference_cases_enabled
            else "[]"
        ),
    )
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
    result, challenge_meta = run_code_challenger(
        item, ideas, candidates, result, client
    )
    return result, {"adjudicator": meta, "challenger": challenge_meta}


def run_code_challenger(
    item: Item,
    ideas: IdeaExtractionResult,
    candidates: dict[int, list[dict]],
    curator: CuratorResult,
    client: OpenAI,
) -> tuple[CuratorResult, dict]:
    """Phản biện ý ngoài codebook và bảo đảm codebook rỗng vẫn khởi tạo được."""
    out_of_codebook = [
        decision for decision in curator.decisions if decision.decision == "OUT_OF_CODEBOOK"
    ]
    if not out_of_codebook:
        return curator, {"skipped": True, "reason": "no_out_of_codebook"}

    cases = []
    for decision in out_of_codebook:
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
            )
            if settings.reference_cases_enabled
            else "[]"
        ),
    )
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
    replacements = {decision.idea_index: decision for decision in challenged.decisions}
    source_by_index = {decision.idea_index: decision for decision in out_of_codebook}
    for idea_index, source in source_by_index.items():
        replacement = replacements.get(idea_index, source)
        allowed_ids = _candidate_ids(candidates, idea_index)
        invalid_match = (
            replacement.decision == "MATCH_EXISTING"
            and replacement.existing_code_id not in allowed_ids
        )
        idea = ideas.ideas[idea_index] if idea_index < len(ideas.ideas) else None
        weak_match_reason = (
            _match_review_reason(idea, replacement, candidates)
            if idea is not None and not invalid_match
            else None
        )
        if (
            not allowed_ids
            and idea is not None
            and idea.status == "VALID"
            and idea.uses_target_object
            and _core_signature_complete(idea)
            and (invalid_match or replacement.decision in {"OUT_OF_CODEBOOK", "UNCERTAIN"})
        ):
            replacements[idea_index] = _bootstrap_new_code(item, idea, replacement)
        elif invalid_match or weak_match_reason:
            replacements[idea_index] = replacement.model_copy(
                update={
                    "decision": "UNCERTAIN",
                    "existing_code_id": None,
                    "reason": (
                        "Challenger chưa chứng minh được MATCH an toàn: "
                        + (
                            "code không thuộc tập ứng viên hợp lệ."
                            if invalid_match
                            else str(weak_match_reason)
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
                    ]
                }
            )
    final = [
        replacements.get(decision.idea_index, decision)
        if decision.decision == "OUT_OF_CODEBOOK"
        else decision
        for decision in curator.decisions
    ]
    return CuratorResult(decisions=final), meta
