"""Truy xuất mã gần nhất bằng vector nhẹ và chữ ký chức năng có cấu trúc."""

from __future__ import annotations

import re
import unicodedata

from openai import OpenAI

from app.config import settings
from app.pipeline.embedding import embed_texts, embedding_model, local_embedding
from app.schemas.schemas import FunctionalSignature, IdeaExtractionResult


def normalize_text(value: str) -> str:
    plain = unicodedata.normalize("NFD", (value or "").casefold())
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def functional_key(signature: FunctionalSignature | dict) -> str:
    data = (
        signature.model_dump()
        if isinstance(signature, FunctionalSignature)
        else FunctionalSignature.model_validate(signature or {}).model_dump()
    )
    return "|".join(normalize_text(data[field]) for field in ("goal", "object_role", "mechanism"))


def signature_text(signature: FunctionalSignature | dict) -> str:
    data = (
        signature.model_dump()
        if isinstance(signature, FunctionalSignature)
        else FunctionalSignature.model_validate(signature or {}).model_dump()
    )
    return " ".join(value for value in data.values() if value)


def core_signature_text(signature: FunctionalSignature | dict) -> str:
    """Văn bản embedding chỉ chứa chức năng cốt lõi, không chứa nhãn hay câu chuẩn hoá."""
    data = (
        signature.model_dump()
        if isinstance(signature, FunctionalSignature)
        else FunctionalSignature.model_validate(signature or {}).model_dump()
    )
    return (
        f"Mục đích: {data['goal']}\n"
        f"Vai trò của vật: {data['object_role']}\n"
        f"Cơ chế: {data['mechanism']}"
    ).strip()


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _field_similarity(left: str, right: str) -> float:
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def signature_similarity(
    left: FunctionalSignature | dict,
    right: FunctionalSignature | dict,
) -> dict[str, float]:
    """So sánh ba thành phần chức năng cốt lõi để kiểm toán quyết định MATCH."""
    left_signature = (
        left
        if isinstance(left, FunctionalSignature)
        else FunctionalSignature.model_validate(left or {})
    )
    right_signature = (
        right
        if isinstance(right, FunctionalSignature)
        else FunctionalSignature.model_validate(right or {})
    )
    fields = {
        "goal": _field_similarity(left_signature.goal, right_signature.goal),
        "object_role": _field_similarity(
            left_signature.object_role, right_signature.object_role
        ),
        "mechanism": _field_similarity(
            left_signature.mechanism, right_signature.mechanism
        ),
    }
    fields["weighted"] = (
        0.40 * fields["goal"]
        + 0.30 * fields["object_role"]
        + 0.30 * fields["mechanism"]
    )
    return {key: round(value, 6) for key, value in fields.items()}


def rank_code_candidates(
    extraction: IdeaExtractionResult,
    codes: list[dict],
    *,
    limit: int | None = None,
    embedding_client: OpenAI | None = None,
) -> dict[int, list[dict]]:
    """Lấy candidate bằng semantic embedding; Curator mới quyết định quan hệ."""
    valid_rows = [
        (index, idea)
        for index, idea in enumerate(extraction.ideas)
        if idea.status == "VALID" and idea.uses_target_object
    ]
    if not valid_rows:
        return {}

    active_model = embedding_model(embedding_client)
    query_texts = [core_signature_text(idea.functional_signature) for _, idea in valid_rows]
    stale_codes = [
        code
        for code in codes
        if not code.get("embedding") or code.get("embedding_model") != active_model
    ]
    code_texts = [
        core_signature_text(code.get("functional_signature") or {})
        if functional_key(code.get("functional_signature") or {}).strip("|")
        else f"{code.get('name', '')} {code.get('description', '')}".strip()
        for code in stale_codes
    ]
    batch = embed_texts([*query_texts, *code_texts], embedding_client)
    query_vectors = batch.vectors[: len(query_texts)]
    for (_, idea), vector in zip(valid_rows, query_vectors):
        idea.embedding = vector
        idea.embedding_model = batch.model
    for code, vector in zip(stale_codes, batch.vectors[len(query_texts) :]):
        code["embedding"] = vector
        code["embedding_model"] = batch.model

    candidate_limit = min(limit or settings.code_candidate_limit, len(codes))

    ranked: dict[int, list[dict]] = {}
    for (index, idea), query_vector in zip(valid_rows, query_vectors):
        query_signature = idea.functional_signature
        rows: list[tuple[float, dict]] = []
        for code in codes:
            code_signature = FunctionalSignature.model_validate(code.get("functional_signature") or {})
            code_vector = code.get("embedding") or []
            similarities = signature_similarity(query_signature, code_signature)
            structural = similarities["weighted"]
            semantic = max(cosine(query_vector, code_vector), 0.0)
            if settings.centroid_retrieval_enabled and not code.get("drift_flag"):
                centroid = code.get("centroid") or []
                if code.get("centroid_model") == batch.model:
                    semantic = max(semantic, cosine(query_vector, centroid))
                    semantic = max([
                        semantic,
                        *(cosine(query_vector, prototype) for prototype in code.get("prototype_vectors") or []),
                    ])
            score = 0.75 * semantic + 0.25 * structural
            # Vector chỉ phục vụ retrieval; không gửi hàng nghìn số thực vào prompt.
            candidate = {
                key: value
                for key, value in code.items()
                if key not in {"embedding", "embedding_model", "centroid", "prototype_vectors", "centroid_model", "drift_flag"}
            }
            candidate.update(
                retrieval_score=round(score, 6),
                semantic_similarity=round(semantic, 6),
                signature_similarity=similarities,
            )
            rows.append((score, candidate))
        rows.sort(key=lambda row: (-row[0], row[1].get("id", "")))
        ranked[index] = [row for _, row in rows[:candidate_limit]]
    return ranked
