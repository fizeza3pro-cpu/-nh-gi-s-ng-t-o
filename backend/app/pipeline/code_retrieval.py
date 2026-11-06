"""Truy xuất mã bằng vector câu gốc và ba vector chức năng riêng biệt."""

from __future__ import annotations

import re
import unicodedata
import hashlib
import json

from openai import OpenAI

from app.config import settings
from app.pipeline.embedding import embed_texts, embedding_model, local_embedding, response_embedding_text
from app.schemas.schemas import FunctionalSignature, IdeaExtractionResult

RETRIEVAL_PROFILE = "raw-fields-v2"
SIGNATURE_WEIGHTS = {"goal": 0.4, "object_role": 0.3, "mechanism": 0.3}
_FIELD_LABELS = {"goal": "Mục đích", "object_role": "Vai trò của vật", "mechanism": "Cơ chế"}


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
    """Độ trùng từ cho heuristic/audit legacy; candidate mới dùng cosine từng trường."""
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
    """Xếp hạng bằng câu gốc/tâm nhóm và ba vector chức năng độc lập."""
    valid_rows = [
        (index, idea)
        for index, idea in enumerate(extraction.ideas)
        if idea.status == "VALID"
    ]
    if not valid_rows:
        return {}

    queries = [{"text": response_embedding_text(idea.original, idea.object_used),
                "functional_signature": idea.functional_signature.model_dump()}
               for _, idea in valid_rows]
    code_rows = [{**code, "text": code_definition_text(code)} for code in codes]
    _embed_representations([*queries, *code_rows], embedding_client)
    for (_, idea), query in zip(valid_rows, queries):
        idea.embedding, idea.embedding_model = query["embedding"], query["embedding_model"]
    for code, row in zip(codes, code_rows):
        for key in ("embedding", "embedding_model", "signature_embeddings"):
            code[key] = row[key]

    candidate_limit = min(limit or settings.code_candidate_limit, len(codes))

    ranked: dict[int, list[dict]] = {}
    for (index, idea), query in zip(valid_rows, queries):
        query_signature = idea.functional_signature
        query_vector = query["embedding"]
        rows: list[tuple[float, dict]] = []
        for code in codes:
            code_signature = FunctionalSignature.model_validate(code.get("functional_signature") or {})
            code_vector = code.get("embedding") or []
            lexical = signature_similarity(query_signature, code_signature)
            similarities = semantic_signature_similarity(query["signature_embeddings"], code["signature_embeddings"])
            definition_similarity = max(cosine(query_vector, code_vector), 0.0)
            semantic, centroid_similarity = definition_similarity, None
            if settings.centroid_retrieval_enabled and not code.get("drift_flag") and not code.get("centroid_dirty"):
                centroid = code.get("centroid") or []
                if code.get("centroid_model") == query["embedding_model"] and centroid and len(centroid) == len(query_vector):
                    # Chỉ dùng tâm trung bình; một ý đại diện gán nhầm không được tăng điểm mã.
                    centroid_similarity = max(0.0, cosine(query_vector, centroid))
                    semantic = max(semantic, centroid_similarity)
            score = settings.retrieval_raw_weight * semantic + (1 - settings.retrieval_raw_weight) * similarities["weighted"]
            # Vector chỉ phục vụ retrieval; không gửi hàng nghìn số thực vào prompt.
            candidate = {
                key: value
                for key, value in code.items()
                if key not in {"embedding", "embedding_model", "signature_embeddings", "centroid", "prototype_vectors", "centroid_model", "drift_flag"}
            }
            candidate.update(
                retrieval_score=round(score, 6),
                semantic_similarity=round(semantic, 6),
                signature_similarity=similarities,
                lexical_similarity=lexical,
                definition_similarity=round(definition_similarity, 6),
                text_similarity=round(_field_similarity(idea.original, " ".join([
                    code_definition_text(code), *(code.get("positive_examples") or [])[:2]
                ])), 6),
                centroid_similarity=round(centroid_similarity, 6) if centroid_similarity is not None else None,
                retrieval_profile=RETRIEVAL_PROFILE,
                raw_weight=settings.retrieval_raw_weight,
                embedding_model=query["embedding_model"],
            )
            rows.append((score, candidate))
        rows.sort(key=lambda row: (-row[0], row[1].get("id", "")))
        ranked[index] = [row for _, row in rows[:candidate_limit]]
    return ranked


def code_definition_text(code: dict) -> str:
    """Định nghĩa là điểm neo câu văn khi chưa có tâm câu gốc đủ điều kiện."""
    text = " ".join(str(code.get(key) or "").strip() for key in ("name", "description")).strip() or core_signature_text(code.get("functional_signature") or {})
    return response_embedding_text(text, code.get("item_name") or "")


def select_diverse_candidates(rows: list[dict], limit: int, *, required_ids=()) -> list[dict]:
    """Giữ mã được chọn và lấy ứng viên từ nhiều kênh; điểm chỉ quyết định thứ tự hiển thị."""
    if limit <= 0:
        return []
    if settings.retrieval_rank_fusion_enabled:
        return reciprocal_rank_candidates(rows, limit, required_ids=required_ids)
    required = set(required_ids)
    selected = {row["id"]: row for row in rows if row["id"] in required}
    channels = [
        sorted(rows, key=lambda row: (-float(row.get("retrieval_score") or 0), row["id"])),
        sorted(rows, key=lambda row: (-float((row.get("signature_similarity") or {}).get("goal") or 0), row["id"])),
        sorted(rows, key=lambda row: (-float(row.get("definition_similarity") or row.get("semantic_similarity") or 0), row["id"])),
        sorted(rows, key=lambda row: (-float((row.get("signature_similarity") or {}).get("weighted") or 0), row["id"])),
        sorted(rows, key=lambda row: (-float(row.get("text_similarity") or 0), row["id"])),
    ]
    # Không thêm một mã tùy ý theo ID khi kênh phụ không có tín hiệu.
    channel_scores = [None, lambda row: (row.get("signature_similarity") or {}).get("goal"),
                      lambda row: row.get("definition_similarity") or row.get("semantic_similarity"),
                      lambda row: (row.get("signature_similarity") or {}).get("weighted"),
                      lambda row: row.get("text_similarity")]
    channels = [channel if score is None else [row for row in channel if float(score(row) or 0) > 0]
                for channel, score in zip(channels, channel_scores)]
    for position in range(len(rows)):
        for channel in channels:
            if len(selected) >= limit:
                break
            if position >= len(channel):
                continue
            row = channel[position]
            selected.setdefault(row["id"], row)
        if len(selected) >= limit:
            break
    return sorted(selected.values(), key=lambda row: (-float(row.get("retrieval_score") or 0), row["id"]))


def reciprocal_rank_candidates(rows, limit, *, required_ids=()):
    """Hợp nhất ba kênh, không đếm lại goal và tổng chức năng như hai phiếu độc lập."""
    scores = {row["id"]: 0.0 for row in rows}
    for score in (lambda row: row.get("semantic_similarity"),
                  lambda row: (row.get("signature_similarity") or {}).get("weighted"),
                  lambda row: row.get("text_similarity")):
        ranked = sorted((row for row in rows if float(score(row) or 0) > 0),
                        key=lambda row: (-float(score(row)), row["id"]))
        for rank, row in enumerate(ranked, 1):
            scores[row["id"]] += 1.0 / (60 + rank)
    ordered = sorted(rows, key=lambda row: (-scores[row["id"]], row["id"]))
    required = [row for row in ordered if row["id"] in set(required_ids)]
    selected = {row["id"]: row for row in required[:limit]}
    for row in ordered:
        if len(selected) >= limit:
            break
        selected.setdefault(row["id"], row)
    return [{**row, "fusion_score": scores[row["id"]]} for row in ordered if row["id"] in selected]


def _representation_digest(row: dict) -> str:
    value = {"text": row["text"], "signature": FunctionalSignature.model_validate(row.get("functional_signature") or {}).model_dump()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _embed_representations(rows: list[dict], client: OpenAI | None) -> None:
    """Gom câu gốc/định nghĩa và các trường vào một lô; cache theo model và nội dung."""
    model = embedding_model(client)
    pending, texts = [], {}
    for row in rows:
        digest = _representation_digest(row)
        signature = FunctionalSignature.model_validate(row.get("functional_signature") or {}).model_dump()
        cached = row.get("signature_embeddings") or {}
        if (row.get("embedding_model") == model and row.get("embedding")
                and cached.get("model") == model and cached.get("digest") == digest
                and all(not signature[field] or cached.get(field) for field in SIGNATURE_WEIGHTS)):
            continue
        inputs = {"raw": " ".join(row["text"].split()) or "(trống)", **{
            field: f"{_FIELD_LABELS[field]}: {value}" for field, value in signature.items() if value}}
        for value in inputs.values():
            texts.setdefault(value, len(texts))
        pending.append((row, digest, inputs))
    if not pending:
        return
    batch = embed_texts(list(texts), client)
    for row, digest, inputs in pending:
        row["embedding"] = batch.vectors[texts[inputs["raw"]]]
        row["embedding_model"] = batch.model
        row["signature_embeddings"] = {"model": batch.model, "digest": digest, **{
            field: batch.vectors[texts[inputs[field]]] if field in inputs else [] for field in SIGNATURE_WEIGHTS}}


def prepare_code_embeddings(codes: list[dict], client: OpenAI | None) -> None:
    """Sinh cache mã mới/mở rộng theo cùng biểu diễn với retrieval, không tin vector từ LLM."""
    rows = [{**code, "text": code_definition_text(code)} for code in codes]
    _embed_representations(rows, client)
    for code, row in zip(codes, rows):
        for key in ("embedding", "embedding_model", "signature_embeddings"):
            code[key] = row[key]


def semantic_signature_similarity(left: dict, right: dict) -> dict[str, float]:
    """So cùng trường; trường thiếu cho 0, không embedding chuỗi rỗng thành bằng chứng."""
    compatible = left.get("model") and left.get("model") == right.get("model")
    fields = {field: max(0.0, min(1.0, cosine(left.get(field) or [], right.get(field) or []))) if compatible else 0.0
              for field in SIGNATURE_WEIGHTS}
    fields["weighted"] = sum(weight * fields[field] for field, weight in SIGNATURE_WEIGHTS.items())
    return {key: round(value, 6) for key, value in fields.items()}
