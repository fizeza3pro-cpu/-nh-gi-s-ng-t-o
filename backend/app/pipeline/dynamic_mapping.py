"""Tầng mapping động: tách ý trước, sau đó dùng Code Curator để gán/tạo code."""

import json
import hashlib
import re
import unicodedata
from itertools import combinations
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.pipeline.code_retrieval import (
    normalize_text,
    rank_code_candidates,
    signature_similarity,
    prepare_code_embeddings,
    RETRIEVAL_PROFILE,
)
from app.pipeline.llm import LLMJSONError, chat_json
from app.schemas.schemas import (
    CuratorDecision,
    CuratorResult,
    ExtractedIdea,
    IdeaExtractionResult,
    Item,
    ReconciliationResult,
    FunctionalSignature,
)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_EXTRACTION_TEMPLATE = (_PROMPT_DIR / "idea_extraction.txt").read_text(encoding="utf-8")
_CURATOR_TEMPLATE = (_PROMPT_DIR / "code_curator.txt").read_text(encoding="utf-8")
_CHALLENGER_TEMPLATE = (_PROMPT_DIR / "code_challenger.txt").read_text(encoding="utf-8")
_BOUNDARY_REPAIR_TEMPLATE = (_PROMPT_DIR / "code_boundary_repair.txt").read_text(
    encoding="utf-8"
)
EXTRACTION_CONTRACT_VERSION = 3
_BATCH_RECONCILER_TEMPLATE = (_PROMPT_DIR / "code_batch_reconciler.txt").read_text(
    encoding="utf-8"
)

_MATCH_RELATIONS = {"SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE"}
_REVIEWABLE_DECISIONS = {
    "OUT_OF_CODEBOOK",
    "UNCERTAIN",
    "EXPAND_EXISTING",
    "INVALID",
}

_CORE_SIGNATURE_FIELDS = ("goal", "object_role", "mechanism")


def _failure_meta(exc: Exception, fallback: dict | None = None) -> dict:
    """Giữ usage/latency của cả lời gọi thất bại để không mất dấu chi phí."""
    metadata = getattr(exc, "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else dict(fallback or {})


def _ground_functional_evidence(idea: ExtractedIdea) -> ExtractedIdea:
    """Chỉ giữ trích dẫn có trong câu gốc và đánh dấu phần LLM phải suy diễn."""
    normalized_original = normalize_text(idea.original)
    evidence: dict[str, str] = {}
    inferred = set(idea.inferred_signature_fields)
    for field in _CORE_SIGNATURE_FIELDS:
        raw = " ".join(str((idea.functional_evidence or {}).get(field) or "").split())
        if raw and normalize_text(raw) in normalized_original:
            evidence[field] = raw
        else:
            evidence[field] = ""
            if getattr(idea.functional_signature, field).strip():
                inferred.add(field)
    return idea.model_copy(
        update={
            "functional_evidence": evidence,
            "inferred_signature_fields": sorted(inferred),
        }
    )


def _creation_goal_is_grounded(idea: ExtractedIdea) -> bool:
    """Chặn thao tác biến đổi trần, không đồng nhất khái quát ngữ nghĩa với việc bịa mục đích."""
    evidence = idea.functional_evidence or {}
    evidence_is_tracked = any(field in evidence for field in _CORE_SIGNATURE_FIELDS)
    if not evidence_is_tracked:
        # Giữ tương thích dữ liệu/test cũ chưa lưu evidence; mọi extraction mới đều đi qua
        # `_ground_functional_evidence` và vì vậy luôn có đủ ba khóa để kiểm tra nghiêm ngặt.
        return "goal" not in idea.inferred_signature_fields
    if str(evidence.get("goal") or "").strip() or "goal" not in idea.inferred_signature_fields:
        return True

    # Extraction chịu trách nhiệm adequacy. Backend chỉ phủ quyết mẫu hẹp có thể xác định chắc chắn:
    # câu chỉ nói cắt/xé/đập... nhưng không nêu dùng phần thu được để làm gì. Các câu ngắn như
    # "trùm lên đầu", "tặng cho..." hoặc "làm nguyên liệu đốt" vẫn đã phát biểu mục đích sử dụng.
    # Giữ dấu tiếng Việt ở đây: chuẩn hoá bỏ dấu làm "bẻ" và "bè" cùng thành
    # ``be``, khiến câu "trùm lên đầu bạn bè" bị hiểu nhầm là thao tác phá huỷ.
    source_tokens = set(re.findall(r"\w+", idea.original.casefold(), flags=re.UNICODE))
    destructive_actions = {"cắt", "xé", "đập", "nghiền", "tháo", "bẻ", "chặt"}
    purpose_markers = {"để", "làm", "lấy", "nhằm", "giúp", "phục"}
    is_bare_transformation = bool(source_tokens & destructive_actions) and not bool(
        source_tokens & purpose_markers
    )
    return not is_bare_transformation


def _one_decision_per_index(
    curator: CuratorResult, expected_indices: set[int]
) -> tuple[CuratorResult, set[int], set[int]]:
    """Loại toàn bộ index bị lặp; không dùng quy tắc lấy phần tử cuối làm lệch ý."""
    counts: dict[int, int] = {}
    for decision in curator.decisions:
        counts[decision.idea_index] = counts.get(decision.idea_index, 0) + 1
    duplicate_indices = {
        idea_index for idea_index, count in counts.items() if count != 1
    }
    unexpected_indices = set(counts) - expected_indices
    accepted = [
        decision
        for decision in curator.decisions
        if decision.idea_index in expected_indices
        and decision.idea_index not in duplicate_indices
    ]
    return CuratorResult(decisions=accepted), duplicate_indices, unexpected_indices


def _guard_ungrounded_creations(
    curator: CuratorResult, ideas: IdeaExtractionResult
) -> CuratorResult:
    """Không cho một mục đích do LLM tự bổ sung trở thành mã được chấp nhận tự động."""
    guarded: list[CuratorDecision] = []
    for decision in curator.decisions:
        idea = (
            ideas.ideas[decision.idea_index]
            if decision.idea_index < len(ideas.ideas)
            else None
        )
        if (
            decision.decision == "CREATE_NEW"
            and idea is not None
            and not _creation_goal_is_grounded(idea)
        ):
            guarded.append(
                decision.model_copy(
                    update={
                        "decision": "UNCERTAIN",
                        "code_relation": "UNCERTAIN",
                        "existing_code_id": None,
                        "policy_gates": {
                            **decision.policy_gates,
                            "goal_grounded_in_source": False,
                        },
                        "reason": (
                            "Không tự tạo mã vì mục đích chức năng không có bằng chứng trong câu gốc; "
                            "mục đích hiện tại do AI suy diễn."
                        ),
                    }
                )
            )
        else:
            guarded.append(decision)
    return CuratorResult(decisions=guarded)


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


def _candidate_prompt_view(candidate: dict) -> dict:
    """Chỉ gửi dữ liệu cần để phân xử, không nhúng toàn bộ bản ghi code vào prompt."""
    return {
        "id": candidate.get("id"),
        "name": candidate.get("name"),
        "description": str(candidate.get("description") or "")[:320],
        "functional_signature": FunctionalSignature.model_validate(candidate.get("functional_signature") or {}).model_dump(),
        "inclusion_rules": list(candidate.get("inclusion_rules") or [])[:2],
        "exclusion_rules": list(candidate.get("exclusion_rules") or [])[:2],
        "positive_examples": list(candidate.get("positive_examples") or [])[:2],
        "retrieval_score": candidate.get("retrieval_score"),
        "semantic_similarity": candidate.get("semantic_similarity"),
        "signature_similarity": candidate.get("signature_similarity") or {},
    }


def _shared_candidate_payload(cases: list[dict], *, key: str = "ideas") -> str:
    """Mỗi định nghĩa mã chỉ xuất hiện một lần; quyền chọn mã vẫn riêng cho từng ý."""
    catalog, rows = {}, []
    for case in cases:
        references = []
        for candidate in case.get("nearest_codes", []):
            code_id = candidate["id"]
            catalog.setdefault(code_id, {k: v for k, v in candidate.items()
                if k not in {"retrieval_score", "semantic_similarity", "signature_similarity"}})
            # Điểm thành phần dùng cho guard/audit backend; Curator chỉ cần thứ hạng và điểm retrieval.
            references.append({"code_id": code_id, **({"retrieval_score": candidate["retrieval_score"]}
                if "retrieval_score" in candidate else {})})
        rows.append({**{k: v for k, v in case.items() if k != "nearest_codes"}, "candidates": references})
    return json.dumps({"codes": list(catalog.values()), key: rows}, ensure_ascii=False, separators=(",", ":"))


def _category_signature(signature):
    """Chữ ký ý và mã cùng contract ba trường; phạm vi mã do Curator khái quát."""
    return signature.model_copy()


def _hydrate_curator_decision(decision: CuratorDecision, idea: ExtractedIdea) -> CuratorDecision:
    """Chỉ bổ sung dữ liệu nguồn thật; không bù chữ ký mã mới bằng chữ ký của ý."""
    update = {}
    if decision.decision in {"CREATE_NEW", "EXPAND_EXISTING"}:
        update["functional_signature"] = _category_signature(decision.functional_signature)
        update["positive_examples"] = [idea.original]
    elif not decision.functional_signature.goal.strip():
        update["functional_signature"] = idea.functional_signature
    return decision.model_copy(update=update) if update else decision


def _match_signal_snapshot(
    candidates: dict[int, list[dict]], idea_index: int, code_id: str | None
) -> dict | None:
    """Tính rank và margin bằng code để LLM không thể tự khai một match mạnh."""
    rows = candidates.get(idea_index, [])
    selected_index = next(
        (
            index
            for index, candidate in enumerate(rows)
            if str(candidate.get("id")) == code_id
        ),
        None,
    )
    if selected_index is None:
        return None
    selected = rows[selected_index]
    selected_score = float(selected.get("retrieval_score") or 0.0)
    alternative_score = max(
        (
            float(candidate.get("retrieval_score") or 0.0)
            for index, candidate in enumerate(rows)
            if index != selected_index
        ),
        default=0.0,
    )
    similarities = selected.get("signature_similarity") or {}
    alternative_similarities = [
        candidate.get("signature_similarity") or {}
        for index, candidate in enumerate(rows)
        if index != selected_index
    ]
    return {
        "rank": selected_index + 1,
        "retrieval_score": selected_score,
        "semantic_similarity": float(selected.get("semantic_similarity") or 0.0),
        "margin": selected_score - alternative_score,
        "signature_similarity": similarities,
        "goal_lead": float(similarities.get("goal") or 0.0)
        - max(
            (float(row.get("goal") or 0.0) for row in alternative_similarities),
            default=0.0,
        ),
        "structural_lead": float(similarities.get("weighted") or 0.0)
        - max(
            (float(row.get("weighted") or 0.0) for row in alternative_similarities),
            default=0.0,
        ),
    }


def _low_margin_is_resolved_by_function(signal: dict, floor: float) -> bool:
    """Cho phép margin vector thấp khi code đầu vượt rõ đối thủ ở chức năng cốt lõi."""
    if signal["margin"] >= floor:
        return True
    similarities = signal["signature_similarity"]
    goal = float(similarities.get("goal") or 0.0)
    structural = float(similarities.get("weighted") or 0.0)
    return (
        goal >= 0.40
        and signal["goal_lead"] >= 0.25
        and structural >= settings.auto_match_structural_floor
    ) or (
        structural >= 0.45 and signal["structural_lead"] >= 0.20
    )


def _match_signal_reason(
    candidates: dict[int, list[dict]],
    decision: CuratorDecision,
    *,
    challenged: bool,
) -> str | None:
    """Áp cổng số cho MATCH trực tiếp và MATCH đã qua Challenger."""
    signal = _match_signal_snapshot(
        candidates, decision.idea_index, decision.existing_code_id
    )
    if signal is None:
        return "Không tính được tín hiệu retrieval cho code được chọn."
    if decision.pair_verified:
        return None
    if decision.confidence < 0.5:
        return "MATCH thiếu độ tin cậy; cần đối chiếu cặp."
    candidate = _candidate_by_id(candidates, decision.idea_index, decision.existing_code_id)
    if candidate and candidate.get("retrieval_profile") == RETRIEVAL_PROFILE:
        # Điểm mới chỉ xếp hạng; finalize sẽ kiểm chứng độc lập, không dùng lại ngưỡng lexical cũ.
        return "MATCH theo biểu diễn mới cần kiểm chứng ngữ nghĩa độc lập." if challenged else None
    if signal["rank"] != 1:
        return f"Code được chọn chỉ đứng hạng {signal['rank']} trong retrieval."

    if challenged:
        floors = (
            ("retrieval", signal["retrieval_score"], settings.challenged_match_retrieval_floor),
            ("semantic", signal["semantic_similarity"], settings.challenged_match_semantic_floor),
        )
        margin_floor = settings.challenged_match_margin_floor
    else:
        similarities = signal["signature_similarity"]
        floors = (
            ("retrieval", signal["retrieval_score"], settings.auto_match_retrieval_floor),
            ("semantic", signal["semantic_similarity"], settings.auto_match_semantic_floor),
            ("goal", float(similarities.get("goal") or 0.0), settings.auto_match_goal_floor),
            (
                "structural",
                float(similarities.get("weighted") or 0.0),
                settings.auto_match_structural_floor,
            ),
        )
        margin_floor = settings.auto_match_margin_floor
    failed = [
        f"{name}={value:.3f} < {floor:.3f}"
        for name, value, floor in floors
        if value < floor
    ]
    if not _low_margin_is_resolved_by_function(signal, margin_floor):
        failed.append(f"margin={signal['margin']:.3f} < {margin_floor:.3f}")
    return "Tín hiệu MATCH chưa đạt ngưỡng: " + ", ".join(failed) if failed else None


def _stored_match_review_reason(idea, decision: CuratorDecision) -> str | None:
    """Chốt MATCH từ snapshot đã lưu, dùng ngay trước transaction ghi database."""
    if decision.decision != "MATCH_EXISTING" or not decision.retrieval_candidates:
        return None
    if decision.confidence < 0.50 and not decision.pair_verified:
        return f"Độ tin cậy MATCH quá thấp: {decision.confidence:.3f} < 0.500."
    candidates = {
        decision.idea_index: [
            {
                "id": row.get("code_id"),
                **{key: value for key, value in row.items() if key != "code_id"},
            }
            for row in decision.retrieval_candidates
        ]
    }
    return _match_review_reason(idea, decision, candidates, challenged=True)


def _match_review_reason(
    idea,
    decision: CuratorDecision,
    candidates: dict[int, list[dict]],
    *,
    challenged: bool = False,
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
            and row.get("source") != "BACKEND_MATCH_GUARD"
        ),
        None,
    )
    # Output mới chỉ trả lựa chọn cuối. Nếu model cũ vẫn gửi bảng đánh giá thì
    # tiếp tục kiểm tra mâu thuẫn, nhưng không bắt model lặp bảng này nữa.
    if evaluation is not None:
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
            for field in ("role_match", "mechanism_match")
        ):
            return "MATCH_EXISTING cần khớp mục đích và ít nhất vai trò hoặc cơ chế."
        matched_candidates = [
            row
            for row in decision.existing_code_evaluations
            if isinstance(row, dict)
            and row.get("source") != "BACKEND_MATCH_GUARD"
            and str(row.get("verdict") or "").upper() == "MATCH"
            and str(row.get("relation") or "") in _MATCH_RELATIONS
        ]
        if len(matched_candidates) != 1:
            return "MATCH_EXISTING chỉ hợp lệ khi đúng một code được kết luận bao phủ ý."
    return _match_signal_reason(candidates, decision, challenged=challenged)


def _match_guard_evidence(
    idea,
    decision: CuratorDecision,
    candidates: dict[int, list[dict]],
    *,
    challenged: bool = False,
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
    signal = _match_signal_snapshot(
        candidates, decision.idea_index, decision.existing_code_id
    ) or {}
    return {
        "source": "BACKEND_MATCH_GUARD",
        "code_id": decision.existing_code_id,
        "relation": decision.code_relation,
        "retrieval_score": float(candidate.get("retrieval_score") or 0.0),
        "semantic_similarity": float(candidate.get("semantic_similarity") or 0.0),
        "code_relation": decision.code_relation,
        "signature_similarity": similarities,
        "selected_rank": signal.get("rank"),
        "margin": round(float(signal.get("margin") or 0.0), 6),
        "retrieval_profile": candidate.get("retrieval_profile"),
        "gate_profile": ("SEMANTIC_PROOF" if candidate.get("retrieval_profile") == RETRIEVAL_PROFILE
                         else "CHALLENGED" if challenged else "AUTO"),
        "verdict": ("PENDING_SEMANTIC_CHECK" if candidate.get("retrieval_profile") == RETRIEVAL_PROFILE
                    and not decision.pair_verified else "PASS"),
    }


def _normalize_curator_contract(
    curator: CuratorResult,
    ideas: IdeaExtractionResult,
    candidates: dict[int, list[dict]],
) -> CuratorResult:
    """Đưa MATCH sai hợp đồng hoặc quá yếu sang Challenger trước khi lưu."""
    normalized = []
    for decision in curator.decisions:
        decision = decision.model_copy(update={"pair_verified": False})
        retrieval_snapshot = [
            {
                "code_id": candidate.get("id"),
                "name": candidate.get("name"),
                "retrieval_score": candidate.get("retrieval_score"),
                "semantic_similarity": candidate.get("semantic_similarity"),
                "signature_similarity": candidate.get("signature_similarity") or {},
                **{key: candidate.get(key) for key in ("retrieval_profile", "lexical_similarity", "definition_similarity", "centroid_similarity", "raw_weight", "embedding_model")},
                "exclusion_rules": candidate.get("exclusion_rules") or [],
            }
            for candidate in candidates.get(decision.idea_index, [])
        ]
        allowed_ids = _candidate_ids(candidates, decision.idea_index)
        idea = (
            ideas.ideas[decision.idea_index]
            if decision.idea_index < len(ideas.ideas)
            else None
        )
        update = {
            "retrieval_candidates": retrieval_snapshot,
            "nearest_code_ids": sorted(allowed_ids),
        }
        if idea is not None:
            decision = _hydrate_curator_decision(decision, idea)
        decision = decision.model_copy(update=update)
        if decision.decision == "INVALID" and idea is not None and idea.status == "VALID":
            decision = decision.model_copy(update={
                "decision": "UNCERTAIN", "code_relation": "UNCERTAIN",
                "reason": "Extraction đã xác nhận công dụng; cần phân loại lại, không loại vì sáng tạo thấp. " + decision.reason,
            })
        invalid_id = (
            decision.decision in {"MATCH_EXISTING", "EXPAND_EXISTING"}
            and decision.existing_code_id not in allowed_ids
        )
        review_reason = (
            _match_review_reason(idea, decision, candidates, challenged=False)
            if idea is not None and not invalid_id
            else None
        )
        if idea is not None and decision.source_text and decision.source_text != idea.original:
            review_reason = "Quyết định không giữ đúng câu nguồn; cần phân xử riêng."
        invalid_expand_relation = (
            decision.decision == "EXPAND_EXISTING"
            and decision.code_relation != "IDEA_BROADER_THAN_CODE"
        )
        if invalid_id or review_reason or invalid_expand_relation:
            normalized.append(
                decision.model_copy(
                    update={
                        "decision": "UNCERTAIN",
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
            audit = _match_guard_evidence(
                idea, decision, candidates, challenged=False
            )
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
    return _guard_ungrounded_creations(
        CuratorResult(decisions=normalized), ideas
    )


def run_idea_extraction(
    item: Item,
    responses: list[str] | str,
    client: OpenAI,
    *, checkpoint: dict | None = None,
) -> tuple[IdeaExtractionResult, dict]:
    """Một lượt phân tích, sửa đúng tập dòng sai contract; không xét lại INVALID."""
    lines = [line.strip() for line in (responses.splitlines() if isinstance(responses, str) else responses)
             if line.strip()][:10]
    expected = set(range(len(lines)))
    if not lines:
        return IdeaExtractionResult(ideas=[]), {"skipped": True, "reason": "empty_input"}
    if checkpoint and checkpoint.get("contract_version") != EXTRACTION_CONTRACT_VERSION:
        raise LLMJSONError("Checkpoint thuộc contract cũ; cần xử lý riêng, không tự phân tích lại lịch sử.",
                           metadata={"retryable": False, "error_type": "LegacyExtractionCheckpoint"})

    def prompt_for(indices):
        return _EXTRACTION_TEMPLATE.format(
            item_name=item.name, item_description=item.description,
            responses_json=json.dumps([{"line_index": i, "text": lines[i]} for i in sorted(indices)],
                                      ensure_ascii=False, separators=(",", ":")),
        )

    def accepted_rows(data, indices):
        values = data.get("ideas", []) if isinstance(data, dict) else []
        if not isinstance(values, list):
            return {}
        accepted = {}
        for i in indices:
            rows = [v for v in values if isinstance(v, dict) and type(v.get("line_index")) is int
                    and v["line_index"] == i]
            if len(rows) != 1:
                continue
            try:
                idea = ExtractedIdea.model_validate(rows[0])
            except ValueError:
                continue
            if not idea.normalized.strip():
                continue
            # Câu gốc và định danh luôn do backend gắn; không nhận chỉ dẫn kỹ thuật từ model.
            idea = idea.model_copy(update={"original": lines[i], "line_index": i,
                "idea_id": hashlib.sha256(f"{i}:{lines[i]}".encode()).hexdigest()[:24],
                "duplicate_of_index": None, "review_required": False})
            accepted[i] = _ground_functional_evidence(idea)
        return accepted

    if checkpoint:
        meta = checkpoint.get("metadata", {})
        by_line = accepted_rows(checkpoint, expected)
    else:
        data, meta = chat_json(client, model=settings.active_llm_model,
            temperature=settings.mapping_temperature, prompt=prompt_for(expected),
            provider=settings.llm_provider, reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.max_tokens_for("idea_extraction", len(lines)),
            max_retries=settings.llm_max_retries, stage="idea_extraction",
            include_raw_response=settings.store_raw_llm_response)
        by_line = accepted_rows(data, expected)
    missing = expected - set(by_line)
    repairs = []
    if missing:
        try:
            data, repair_meta = chat_json(client, model=settings.active_llm_model,
                temperature=settings.mapping_temperature, prompt=prompt_for(missing),
                provider=settings.llm_provider, reasoning_effort=settings.active_reasoning_effort,
                max_tokens=settings.max_tokens_for("idea_extraction", len(missing)),
                max_retries=settings.llm_max_retries, stage="extraction_repair")
            repairs.append(repair_meta)
            by_line.update(accepted_rows(data, missing))
            if set(by_line) != expected:
                raise LLMJSONError("Extraction còn thiếu hoặc sai dòng sau một lượt sửa contract.",
                                   metadata={**repair_meta, "error_type": "ExtractionContractError"})
        except LLMJSONError as exc:
            exc.extraction_checkpoint = {"contract_version": EXTRACTION_CONTRACT_VERSION,
                "ideas": [by_line[i].model_dump() for i in sorted(by_line)], "metadata": meta}
            exc.metadata = {**exc.metadata, "previous_extraction": meta}
            raise
    return IdeaExtractionResult(ideas=[by_line[i] for i in sorted(expected)]), {
        **meta, "extraction_repairs": repairs, "contract_version": EXTRACTION_CONTRACT_VERSION,
    }


def _finalize_curator(item, ideas, curator, candidates, client, embedding_client):
    """Giữ snapshot retrieval qua reconciler và đối chiếu ngữ nghĩa trước ghi mã."""
    from app.pipeline.decision_verifier import verify_decisions

    restored = CuratorResult(decisions=[decision.model_copy(update={
        "compared_code_ids": sorted(_candidate_ids(candidates, decision.idea_index)),
        "nearest_code_ids": sorted(_candidate_ids(candidates, decision.idea_index)),
        "retrieval_candidates": [{
            "code_id": c.get("id"), "name": c.get("name"),
            "retrieval_score": c.get("retrieval_score"),
            "semantic_similarity": c.get("semantic_similarity"),
            "signature_similarity": c.get("signature_similarity") or {},
            **{key: c.get(key) for key in ("retrieval_profile", "lexical_similarity", "definition_similarity", "centroid_similarity", "raw_weight", "embedding_model")},
            "exclusion_rules": c.get("exclusion_rules") or [],
        } for c in candidates.get(decision.idea_index, [])],
    }) for decision in curator.decisions])
    checked, meta = verify_decisions(item, ideas, restored, candidates, client)
    checked = _guard_ungrounded_creations(checked, ideas)
    return _attach_decision_embeddings(checked, embedding_client), meta


def run_code_mapping(
    item: Item,
    ideas: IdeaExtractionResult,
    existing_codes: list[dict],
    client: OpenAI,
    embedding_client: OpenAI | None = None,
    *,
    idea_indices: set[int] | None = None,
    _candidates: dict | None = None,
    _skip_reconciliation: bool = False,
) -> tuple[CuratorResult, dict]:
    candidates = _candidates if _candidates is not None else rank_code_candidates(
        ideas,
        existing_codes,
        limit=(len(existing_codes) if len(existing_codes) <= settings.codebook_full_scan_limit else settings.novelty_candidate_limit),
        embedding_client=embedding_client,
    )
    valid_ideas = [
        {
            "idea_index": index,
            "normalized": idea.normalized,
            "original": idea.original,
            "object_used": idea.object_used,
            "functional_signature": idea.functional_signature.model_dump(),
            "functional_evidence": idea.functional_evidence,
            "inferred_signature_fields": idea.inferred_signature_fields,
            "nearest_codes": [
                _candidate_prompt_view(candidate)
                for candidate in candidates.get(index, [])
            ],
        }
        for index, idea in enumerate(ideas.ideas)
        if idea.status == "VALID"
        and (idea_indices is None or index in idea_indices)
    ]
    if not valid_ideas:
        return CuratorResult(decisions=[]), {
            "adjudicator": {"skipped": True, "reason": "no_valid_idea"},
            "challenger": {"skipped": True, "reason": "no_valid_idea"},
            "batch_reconciliation": {"skipped": True, "reason": "no_valid_idea"},
        }
    expected_indices = {int(case["idea_index"]) for case in valid_ideas}
    if len(valid_ideas) > settings.mapping_batch_size:
        decisions, batches = [], []
        ordered = sorted(expected_indices)
        for offset in range(0, len(ordered), settings.mapping_batch_size):
            partial, partial_meta = run_code_mapping(
                item, ideas, existing_codes, client, embedding_client,
                idea_indices=set(ordered[offset:offset + settings.mapping_batch_size]),
                _candidates=candidates, _skip_reconciliation=True,
            )
            decisions.extend(partial.decisions)
            batches.append(partial_meta)
        combined, reconciliation = _reconcile_new_code_batch(
            item=item, ideas=ideas, curator=CuratorResult(decisions=decisions), client=client,
        )
        combined, verification = _finalize_curator(item, ideas, combined, candidates, client, embedding_client)
        return combined, {"batches": batches, "batch_reconciliation": reconciliation, "decision_verifier": verification}
    prompt = _CURATOR_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        ideas_with_candidates_json=_shared_candidate_payload(valid_ideas),
    )
    meta: dict = {}
    batch_failed_and_retried = False
    try:
        data, meta = chat_json(
            client,
            model=settings.active_curator_model,
            temperature=settings.code_curator_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.max_tokens_for("code_curator", len(valid_ideas)),
            max_retries=settings.llm_max_retries,
            stage="code_curator",
            include_raw_response=settings.store_raw_llm_response,
        )
        validated, duplicate_indices, unexpected_indices = _one_decision_per_index(
            CuratorResult.model_validate(data), expected_indices
        )
        if duplicate_indices or unexpected_indices:
            meta = {
                **meta,
                "duplicate_idea_indices": sorted(duplicate_indices),
                "unexpected_idea_indices": sorted(unexpected_indices),
            }
        result = _normalize_curator_contract(validated, ideas, candidates)
    except (LLMJSONError, ValueError) as exc:
        # Batch hỏng không được gọi lại nguyên prompt. Hỏi riêng từng ý với
        # contract ngắn để cô lập lỗi và tránh nhân đôi chi phí của cả lượt.
        batch_failed_and_retried = True
        first_failure = {
            **_failure_meta(exc, meta),
            "failed": True,
            "reason": str(exc),
        }
        recovered: list[CuratorDecision] = []
        retry_metas: list[dict] = []
        for case in valid_ideas:
            retry_prompt = _CURATOR_TEMPLATE.format(
                item_name=item.name,
                item_description=item.description,
                ideas_with_candidates_json=_shared_candidate_payload([case]),
            )
            retry_meta = {}
            try:
                retry_data, retry_meta = chat_json(
                    client,
                    model=settings.active_curator_model,
                    temperature=settings.code_curator_temperature,
                    prompt=retry_prompt,
                    provider=settings.llm_provider,
                    reasoning_effort=settings.active_reasoning_effort,
                    max_tokens=settings.max_tokens_for("code_curator", 1),
                    max_retries=settings.llm_max_retries,
                    stage="code_curator_retry_single",
                    include_raw_response=settings.store_raw_llm_response,
                )
                retried, _, _ = _one_decision_per_index(
                    CuratorResult.model_validate(retry_data),
                    {int(case["idea_index"])},
                )
                recovered.extend(
                    decision
                    for decision in retried.decisions
                    if decision.idea_index == int(case["idea_index"])
                )
                retry_metas.append(retry_meta)
            except (LLMJSONError, ValueError) as retry_exc:
                retry_metas.append(
                    {
                        **_failure_meta(retry_exc, retry_meta),
                        "failed": True,
                        "reason": str(retry_exc),
                        "idea_index": int(case["idea_index"]),
                    }
                )
        meta = {
            "strategy": "retry_each_idea",
            "runs": [first_failure, *retry_metas],
            "initial_failure": first_failure["reason"],
            "failed": not recovered,
        }
        result = _normalize_curator_contract(
            CuratorResult(decisions=recovered), ideas, candidates
        )
        if not result.decisions:
            return CuratorResult(decisions=[]), {
                "adjudicator": meta,
                "challenger": {
                    "skipped": True,
                    "reason": "invalid_curator_output",
                },
                "batch_reconciliation": {
                    "skipped": True,
                    "reason": "invalid_curator_output",
                },
            }
    if not batch_failed_and_retried:
        returned_indices = {decision.idea_index for decision in result.decisions}
        missing_indices = expected_indices - returned_indices
        if missing_indices:
            retry_metas: list[dict] = []
            recovered: list[CuratorDecision] = []
            for case in valid_ideas:
                idea_index = int(case["idea_index"])
                if idea_index not in missing_indices:
                    continue
                retry_prompt = _CURATOR_TEMPLATE.format(
                    item_name=item.name,
                    item_description=item.description,
                    ideas_with_candidates_json=_shared_candidate_payload([case]),
                )
                retry_meta = {}
                try:
                    retry_data, retry_meta = chat_json(
                        client,
                        model=settings.active_curator_model,
                        temperature=settings.code_curator_temperature,
                        prompt=retry_prompt,
                        provider=settings.llm_provider,
                        reasoning_effort=settings.active_reasoning_effort,
                        max_tokens=settings.max_tokens_for("code_curator", 1),
                        max_retries=settings.llm_max_retries,
                        stage="code_curator_retry_missing",
                        include_raw_response=settings.store_raw_llm_response,
                    )
                    retried, _, _ = _one_decision_per_index(
                        CuratorResult.model_validate(retry_data), {idea_index}
                    )
                    recovered.extend(
                        decision
                        for decision in retried.decisions
                        if decision.idea_index == idea_index
                    )
                    retry_metas.append(retry_meta)
                except (LLMJSONError, ValueError) as retry_exc:
                    retry_metas.append(
                        {
                            **_failure_meta(retry_exc, retry_meta),
                            "failed": True,
                            "reason": str(retry_exc),
                            "idea_index": idea_index,
                        }
                    )
            result = _normalize_curator_contract(
                CuratorResult(decisions=[*result.decisions, *recovered]),
                ideas,
                candidates,
            )
            still_missing = expected_indices - {
                decision.idea_index for decision in result.decisions
            }
            meta = {
                "strategy": "retry_missing_ideas",
                "runs": [meta, *retry_metas],
                "initial_missing_indices": sorted(missing_indices),
                "unresolved_indices": sorted(still_missing),
                "failed": bool(still_missing),
            }
    result, boundary_repair_meta = _repair_missing_boundaries(
        item=item,
        cases=valid_ideas,
        challenged=result,
        client=client,
    )
    if boundary_repair_meta is not None:
        meta = {**meta, "boundary_repair": boundary_repair_meta}
    result, challenge_meta = run_code_challenger(
        item, ideas, candidates, result, client, embedding_client
    )
    reconciliation_meta = {"skipped": True}
    if not _skip_reconciliation:
        result, reconciliation_meta = _reconcile_new_code_batch(
            item=item, ideas=ideas, curator=result, client=client,
        )
    # Challenger/Reconciler có thể đề xuất CREATE_NEW trở lại; áp chốt lần cuối trước khi
    # sinh embedding và trước khi kết quả có cơ hội đi vào codebook.
    result = _guard_ungrounded_creations(result, ideas)
    result = CuratorResult(decisions=[decision.model_copy(update={
        "compared_code_ids": sorted(_candidate_ids(candidates, decision.idea_index)),
    }) for decision in result.decisions])
    verification = {"skipped": True, "reason": "partial_batch"}
    if not _skip_reconciliation:
        result, verification = _finalize_curator(item, ideas, result, candidates, client, embedding_client)
    return result, {
        "adjudicator": meta,
        "challenger": challenge_meta,
        "batch_reconciliation": reconciliation_meta,
        "decision_verifier": verification,
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
    codes = [{"name": d.code_name, "description": d.code_description,
              "functional_signature": d.functional_signature.model_dump()} for d in selected]
    prepare_code_embeddings(codes, embedding_client)
    vectors = iter(codes)
    selected_ids = {decision.idea_index for decision in selected}
    decisions = []
    for decision in curator.decisions:
        if decision.idea_index in selected_ids and decision.decision in {
            "CREATE_NEW",
            "EXPAND_EXISTING",
        }:
            vectors_for_code = next(vectors)
            decisions.append(
                decision.model_copy(
                    update={
                        "embedding": vectors_for_code["embedding"],
                        "embedding_model": vectors_for_code["embedding_model"],
                        "signature_embeddings": vectors_for_code["signature_embeddings"],
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


def _has_reusable_scope(
    decision: CuratorDecision, *, source_text: str = ""
) -> bool:
    """Chỉ nhận category có chữ ký cấp nhóm và hai biến thể khác câu nguồn để thử độ bao phủ."""
    source_key = normalize_code_name(source_text)
    variants = {
        normalize_code_name(example)
        for example in decision.scope_variants
        if normalize_code_name(example)
        and normalize_code_name(example) != source_key
    }
    signature = decision.functional_signature
    return (
        bool((decision.code_name or "").strip())
        and bool(decision.code_description.strip())
        and _has_specific_boundaries(decision)
        and all(
            getattr(signature, field).strip()
            for field in ("goal", "object_role", "mechanism")
        )
        and len(variants) >= 2
    )


def _repair_missing_boundaries(
    *,
    item: Item,
    cases: list[dict],
    challenged: CuratorResult,
    client: OpenAI,
) -> tuple[CuratorResult, dict | None]:
    """Gọi lại bằng prompt ngắn khi đề xuất chưa có phạm vi category tái sử dụng được."""
    cases_by_index = {int(case["idea_index"]): case for case in cases}
    incomplete = [
        decision
        for decision in challenged.decisions
        if decision.decision in {"CREATE_NEW", "EXPAND_EXISTING"}
        and not _has_reusable_scope(
            decision,
            source_text=str(
                cases_by_index.get(decision.idea_index, {}).get("original", "")
            ),
        )
    ]
    if not incomplete:
        return challenged, None

    repair_cases = []
    for decision in incomplete:
        case = cases_by_index.get(decision.idea_index, {})
        repair_cases.append(
            {
                "idea_index": decision.idea_index,
                "original": case.get("original", ""),
                "normalized": case.get("normalized", ""),
                "decision_to_preserve": decision.model_dump(
                    include={"decision", "code_relation", "existing_code_id", "code_name", "code_description",
                             "functional_signature", "scope_variants", "inclusion_rules", "exclusion_rules",
                             "absorbed_code_ids", "reason", "confidence"}
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
    meta = {}
    try:
        data, meta = chat_json(
            client,
            model=settings.active_challenger_model,
            temperature=settings.code_curator_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.max_tokens_for("boundary_repair", len(incomplete)),
            max_retries=settings.llm_max_retries,
            stage="boundary_repair",
            include_raw_response=settings.store_raw_llm_response,
        )
        repaired = CuratorResult.model_validate(data)
    except (LLMJSONError, ValueError) as exc:
        # Thiếu ranh giới thì không được tạo/mở rộng code.
        repaired = CuratorResult(decisions=[])
        meta = {**_failure_meta(exc, meta), "failed": True, "reason": str(exc)}
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
        merged_candidate = (
            decision.model_copy(
                update={
                    "code_name": candidate.code_name or decision.code_name,
                    "code_description": (
                        candidate.code_description or decision.code_description
                    ),
                    "functional_signature": _category_signature(
                        candidate.functional_signature
                        if candidate.functional_signature.goal.strip()
                        else decision.functional_signature
                    ),
                    "inclusion_rules": candidate.inclusion_rules,
                    "exclusion_rules": candidate.exclusion_rules,
                    "scope_variants": candidate.scope_variants,
                    "reason": candidate.reason or decision.reason,
                    "confidence": candidate.confidence,
                }
            )
            if candidate is not None
            else None
        )
        if (
            candidate is not None
            and candidate.decision == decision.decision
            and same_target
            and merged_candidate is not None
            and _has_reusable_scope(
                merged_candidate,
                source_text=str(
                    cases_by_index.get(decision.idea_index, {}).get("original", "")
                ),
            )
        ):
            final.append(merged_candidate)
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
                        "Chưa xác lập được category tái sử dụng với chữ ký cấp nhóm, "
                        "biến thể phạm vi và ranh giới bao gồm/loại trừ cụ thể."
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
        same_role_with_shared_function = (
            similarities["object_role"] >= 0.5
            and max(similarities["goal"], similarities["mechanism"]) >= 0.25
        )
        strong_overall_with_shared_structure = (
            similarities["weighted"] >= 0.5
            and max(similarities["object_role"], similarities["mechanism"]) >= 0.5
        )
        if same_role_with_shared_function or strong_overall_with_shared_structure:
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
    overlap_indices = {int(pair[key]) for pair in overlaps for key in ("left_idea_index", "right_idea_index")}
    proposed = [decision for decision in proposed if decision.idea_index in overlap_indices]

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
                        include={"decision", "code_relation", "existing_code_id", "code_name", "code_description",
                                 "functional_signature", "scope_variants", "inclusion_rules", "exclusion_rules",
                                 "absorbed_code_ids", "reason", "confidence"}
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
    meta = {}
    try:
        data, meta = chat_json(
            client,
            model=settings.active_curator_model,
            temperature=settings.code_curator_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.max_tokens_for("batch_reconciler", len(proposed)),
            max_retries=settings.llm_max_retries,
            stage="batch_reconciler",
            include_raw_response=settings.store_raw_llm_response,
        )
        if "groups" in data:
            grouped = ReconciliationResult.model_validate(data)
            expected = {decision.idea_index for decision in proposed}
            seen = []
            grouped_decisions = []
            for group_number, group in enumerate(grouped.groups):
                seen.extend(group.idea_indices)
                for index in group.idea_indices:
                    grouped_decisions.append(group.canonical.model_copy(update={
                        "idea_index": index,
                        "proposal_group": f"batch-{group_number}",
                    }))
            if len(seen) != len(set(seen)) or set(seen) != expected:
                raise ValueError("Reconciler thiếu, trùng hoặc thêm ID.")
            reconciled = CuratorResult(decisions=grouped_decisions)
        else:
            # Chỉ đọc lại output legacy; prompt mới sử dụng groups.
            reconciled, duplicates, unexpected = _one_decision_per_index(
                CuratorResult.model_validate(data), {decision.idea_index for decision in proposed},
            )
            if duplicates or unexpected:
                raise ValueError("Reconciler trả ID không hợp lệ.")
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
            **_failure_meta(exc, meta),
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
        if candidate is not None and idea_index < len(ideas.ideas):
            candidate = _hydrate_curator_decision(candidate, ideas.ideas[idea_index])
        if (
            candidate is not None
            and candidate.decision == "CREATE_NEW"
            and candidate.code_name
            and _has_reusable_scope(
                candidate.model_copy(
                    update={
                        "functional_signature": _category_signature(
                            candidate.functional_signature
                        )
                    }
                ),
                source_text=(
                    ideas.ideas[idea_index].original
                    if idea_index < len(ideas.ideas)
                    else ""
                ),
            )
        ):
            accepted[idea_index] = candidate.model_copy(
                update={
                    "functional_signature": _category_signature(
                        candidate.functional_signature
                    ),
                    "positive_examples": original.positive_examples,
                    "reviewed_by_challenger": True,
                }
            )
        else:
            accepted[idea_index] = original.model_copy(
                update={
                    "decision": "UNCERTAIN",
                    "code_relation": "UNCERTAIN",
                    "reason": "Batch Reconciler không trả category có ranh giới hợp lệ.",
                }
            )

    # Các ý cùng nhóm có khóa proposal riêng để persistence tạo code đúng một lần.
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
        scope_variants = list(
            dict.fromkeys(
                example.strip()
                for decision in group
                for example in decision.scope_variants
                if example.strip()
            )
        )
        for decision in group:
            accepted[decision.idea_index] = decision.model_copy(
                update={
                    "proposal_group": canonical.proposal_group or f"group-{min(d.idea_index for d in group)}",
                    "code_name": canonical.code_name,
                    "code_description": canonical.code_description,
                    "functional_signature": canonical.functional_signature,
                    "inclusion_rules": canonical.inclusion_rules,
                    "exclusion_rules": canonical.exclusion_rules,
                    "positive_examples": examples,
                    "scope_variants": scope_variants,
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
            and not (left.proposal_group and right.proposal_group and left.proposal_group != right.proposal_group)
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
    """Chỉ phân xử các ca mơ hồ, mở rộng phạm vi hoặc mâu thuẫn tính hợp lệ."""
    reviewable = [
        decision
        for decision in curator.decisions
        if decision.decision in _REVIEWABLE_DECISIONS
        and decision.policy_gates.get("goal_grounded_in_source") is not False
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
                },
                "nearest_codes": [
                    _candidate_prompt_view(candidate)
                    for candidate in candidates.get(decision.idea_index, [])
                ],
            }
        )
    if not cases:
        return curator, {"skipped": True, "reason": "invalid_indices"}
    expected_indices = {int(case["idea_index"]) for case in cases}

    prompt = _CHALLENGER_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        codebook_is_empty=str(not any(candidates.values())).lower(),
        challenger_cases_json=_shared_candidate_payload(cases, key="cases"),
    )
    meta: dict = {}
    try:
        data, meta = chat_json(
            client,
            model=settings.active_challenger_model,
            temperature=settings.code_curator_temperature,
            prompt=prompt,
            provider=settings.llm_provider,
            reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.max_tokens_for("code_challenger", len(cases)),
            max_retries=settings.llm_max_retries,
            stage="code_challenger",
            include_raw_response=settings.store_raw_llm_response,
        )
        challenged, duplicate_indices, unexpected_indices = _one_decision_per_index(
            CuratorResult.model_validate(data), expected_indices
        )
        if duplicate_indices or unexpected_indices:
            meta = {
                **meta,
                "duplicate_idea_indices": sorted(duplicate_indices),
                "unexpected_idea_indices": sorted(unexpected_indices),
            }
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
        ), {**_failure_meta(exc, meta), "failed": True, "reason": str(exc)}

    returned_indices = {decision.idea_index for decision in challenged.decisions}
    missing_indices = expected_indices - returned_indices
    if missing_indices:
        retry_cases = [
            case for case in cases if int(case["idea_index"]) in missing_indices
        ]
        retry_prompt = _CHALLENGER_TEMPLATE.format(
            item_name=item.name,
            item_description=item.description,
            codebook_is_empty=str(not any(candidates.values())).lower(),
            challenger_cases_json=_shared_candidate_payload(retry_cases, key="cases"),
        )
        retry_meta = {}
        try:
            retry_data, retry_meta = chat_json(
                client,
                model=settings.active_challenger_model,
                temperature=settings.code_curator_temperature,
                prompt=retry_prompt,
                provider=settings.llm_provider,
                reasoning_effort=settings.active_reasoning_effort,
                max_tokens=settings.max_tokens_for("code_challenger", len(retry_cases)),
                max_retries=settings.llm_max_retries,
                stage="code_challenger_retry_missing",
                include_raw_response=settings.store_raw_llm_response,
            )
            retried, retry_duplicates, retry_unexpected = _one_decision_per_index(
                CuratorResult.model_validate(retry_data), missing_indices
            )
            accepted_retry = [
                decision
                for decision in retried.decisions
                if decision.idea_index in missing_indices
            ]
            challenged = CuratorResult(
                decisions=[*challenged.decisions, *accepted_retry]
            )
            meta = {
                "runs": [meta, retry_meta],
                "strategy": "retry_missing_only",
                "initial_missing_indices": sorted(missing_indices),
                "retry_duplicate_idea_indices": sorted(retry_duplicates),
                "retry_unexpected_idea_indices": sorted(retry_unexpected),
            }
        except (LLMJSONError, ValueError) as exc:
            meta = {
                "runs": [meta, {**_failure_meta(exc, retry_meta), "failed": True}],
                "strategy": "retry_missing_only",
                "initial_missing_indices": sorted(missing_indices),
            }
    hydrated_decisions: list[CuratorDecision] = []
    for decision in challenged.decisions:
        decision = decision.model_copy(update={"pair_verified": False})
        if decision.idea_index >= len(ideas.ideas):
            hydrated_decisions.append(decision)
            continue
        idea = ideas.ideas[decision.idea_index]
        update = {
            "nearest_code_ids": sorted(
                _candidate_ids(candidates, decision.idea_index)
            ),
        }
        decision = _hydrate_curator_decision(decision, idea)
        hydrated_decisions.append(decision.model_copy(update=update))
    challenged = CuratorResult(decisions=hydrated_decisions)
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
        idea = ideas.ideas[idea_index] if idea_index < len(ideas.ideas) else None
        if idea is not None:
            update = {
                "nearest_code_ids": sorted(_candidate_ids(candidates, idea_index)),
            }
            replacement = _hydrate_curator_decision(replacement, idea).model_copy(
                update=update
            )
            replacements[idea_index] = replacement
        allowed_ids = _candidate_ids(candidates, idea_index)
        invalid_match = (
            replacement.decision in {"MATCH_EXISTING", "EXPAND_EXISTING"}
            and replacement.existing_code_id not in allowed_ids
        )
        weak_match_reason = (
            _match_review_reason(
                idea, replacement, candidates, challenged=True
            )
            if idea is not None and not invalid_match
            else None
        )
        if weak_match_reason and not invalid_match and idea is not None:
            from app.pipeline.semantic_verifier import verify_pair, propose_scope
            candidate = _candidate_by_id(candidates, idea_index, replacement.existing_code_id)
            try:
                verdict, pair_meta = verify_pair(item, idea.original, candidate, client)
                meta.setdefault("pair_checks", []).append(pair_meta)
                if verdict.relation == "IDEA_BROADER_THAN_CODE" and verdict.role_match:
                    proposed, scope_meta = propose_scope(item, idea.original, candidate, client)
                    meta.setdefault("scope_proposals", []).append(scope_meta)
                    replacement = _hydrate_curator_decision(proposed, idea).model_copy(update={
                        "idea_index": idea_index, "nearest_code_ids": sorted(allowed_ids),
                    })
                    replacements[idea_index] = replacement
                    source = replacement
                    weak_match_reason = None
                if verdict.relation in _MATCH_RELATIONS and verdict.goal_match and verdict.role_match and not verdict.exclusion_hit:
                    replacement = replacement.model_copy(update={
                        "pair_verified": True, "source_text": idea.original,
                        "code_relation": verdict.relation,
                        "existing_code_evaluations": [{
                            "code_id": replacement.existing_code_id, "relation": verdict.relation,
                            "goal_match": True, "role_match": True, "mechanism_match": True,
                            "excluded_by": "", "verdict": "MATCH", "source": "PAIR_VERIFIER",
                            "evidence": verdict.evidence, "reason": verdict.reason,
                        }],
                    })
                    replacements[idea_index] = replacement
                    weak_match_reason = None
            except (LLMJSONError, ValueError) as exc:
                meta.setdefault("pair_checks", []).append({**_failure_meta(exc), "failed": True})
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
            and source.decision
            not in {"OUT_OF_CODEBOOK", "CREATE_NEW", "UNCERTAIN", "INVALID"}
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
            audit = _match_guard_evidence(
                idea, replacement, candidates, challenged=True
            )
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
                update={
                        "decision": "UNCERTAIN",
                        "reason": "Curator và Challenger bất đồng về tính hợp lệ của ý.",
                }
            )
    final = []
    for decision in curator.decisions:
        resolved = (
            replacements.get(decision.idea_index, decision)
            if decision.decision in _REVIEWABLE_DECISIONS
            else decision
        )
        final.append(
            resolved.model_copy(
                update={"retrieval_candidates": decision.retrieval_candidates}
            )
        )
    return CuratorResult(decisions=final), meta
