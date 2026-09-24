"""Truy xuất mã gần nhất bằng vector nhẹ và chữ ký chức năng có cấu trúc."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata

from app.schemas.schemas import FunctionalSignature, IdeaExtractionResult


_VECTOR_SIZE = 384


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
    return " ".join(
        part
        for part in (
            data["goal"],
            data["object_role"],
            data["mechanism"],
            data["transformation"],
            data["target"],
            data["context"],
        )
        if part
    )


def local_embedding(value: str) -> list[float]:
    """Vector băm có thể tái tạo; functional signature giúp giảm phụ thuộc từ bề mặt."""
    tokens = normalize_text(value).split()
    features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]
    vector = [0.0] * _VECTOR_SIZE
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % _VECTOR_SIZE
        vector[index] += -1.0 if digest[2] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


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
    limit: int = 5,
) -> dict[int, list[dict]]:
    """Lấy top-k để tăng recall; Curator mới là tầng quyết định category."""
    ranked: dict[int, list[dict]] = {}
    for index, idea in enumerate(extraction.ideas):
        if idea.status != "VALID" or not idea.uses_target_object:
            continue
        query_signature = idea.functional_signature
        query_vector = local_embedding(f"{idea.normalized} {signature_text(query_signature)}")
        rows: list[tuple[float, dict]] = []
        for code in codes:
            code_signature = FunctionalSignature.model_validate(code.get("functional_signature") or {})
            code_vector = code.get("embedding") or local_embedding(
                f"{code.get('name', '')} {code.get('description', '')} {signature_text(code_signature)}"
            )
            similarities = signature_similarity(query_signature, code_signature)
            structural = similarities["weighted"]
            score = 0.65 * structural + 0.35 * max(cosine(query_vector, code_vector), 0.0)
            # Embedding chỉ phục vụ xếp hạng cục bộ; gửi 384 số thực vào prompt vừa tốn
            # context vừa làm model chú ý sai vào dữ liệu không có ý nghĩa ngôn ngữ.
            candidate = {key: value for key, value in code.items() if key != "embedding"}
            candidate.update(
                retrieval_score=round(score, 6),
                signature_similarity=similarities,
            )
            rows.append((score, candidate))
        rows.sort(key=lambda row: (-row[0], row[1].get("id", "")))
        ranked[index] = [row for _, row in rows[:limit]]
    return ranked
