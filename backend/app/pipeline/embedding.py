"""Sinh semantic embedding theo lô, tách khỏi ngân sách context của LLM chat."""

from __future__ import annotations

import hashlib
import math
import re
import time
import unicodedata
from dataclasses import dataclass

from openai import OpenAI

from app.config import settings


_LOCAL_VECTOR_SIZE = 384
_LOCAL_MODEL = "local-hash-v1"


class EmbeddingError(RuntimeError):
    """Provider embedding không trả đủ vector hợp lệ."""


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    model: str
    semantic: bool


def _normalize_text(value: str) -> str:
    plain = unicodedata.normalize("NFD", (value or "").casefold())
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def local_embedding(value: str) -> list[float]:
    """Vector băm chỉ dùng cho mock/test hoặc phương án suy giảm đã khai báo rõ."""
    tokens = _normalize_text(value).split()
    features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]
    vector = [0.0] * _LOCAL_VECTOR_SIZE
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % _LOCAL_VECTOR_SIZE
        vector[index] += -1.0 if digest[2] & 1 else 1.0
    norm = math.sqrt(sum(component * component for component in vector))
    return [component / norm for component in vector] if norm else vector


def embedding_model(client: OpenAI | None) -> str:
    """Tên model dùng để nhận biết vector cache có còn tương thích hay không."""
    if client is None or settings.embedding_provider == "local":
        return _LOCAL_MODEL
    return settings.cloudflare_embedding_model


def embed_texts(texts: list[str], client: OpenAI | None = None) -> EmbeddingBatch:
    """Embedding nhiều văn bản; một batch API có thể chứa nhiều ý và code."""
    if not texts:
        return EmbeddingBatch(vectors=[], model=embedding_model(client), semantic=False)
    cleaned = [" ".join((text or "").split()) or "(trống)" for text in texts]
    if client is None or settings.embedding_provider == "local":
        return EmbeddingBatch(
            vectors=[local_embedding(text) for text in cleaned],
            model=_LOCAL_MODEL,
            semantic=False,
        )

    vectors: list[list[float]] = []
    batch_size = settings.embedding_batch_size
    for start in range(0, len(cleaned), batch_size):
        batch = cleaned[start : start + batch_size]
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = client.embeddings.create(
                    model=settings.cloudflare_embedding_model,
                    input=batch,
                )
                ordered = sorted(response.data, key=lambda row: row.index)
                batch_vectors = [list(row.embedding) for row in ordered]
                if len(batch_vectors) != len(batch) or any(not vector for vector in batch_vectors):
                    raise EmbeddingError("Provider trả thiếu semantic embedding.")
                vectors.extend(batch_vectors)
                break
            except Exception as error:  # noqa: BLE001 - cần retry lỗi mạng/provider
                last_error = error
                if attempt < 2:
                    time.sleep(0.5 * (2**attempt))
        else:
            raise EmbeddingError(
                f"Không thể tạo semantic embedding sau 3 lần gọi: {last_error}"
            ) from last_error

    return EmbeddingBatch(
        vectors=vectors,
        model=settings.cloudflare_embedding_model,
        semantic=True,
    )
