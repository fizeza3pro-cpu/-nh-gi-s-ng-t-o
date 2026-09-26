"""Nạp và truy xuất các tình huống mẫu dùng làm án lệ cho pipeline mã hoá."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from openai import OpenAI

from app.config import settings
from app.pipeline.code_retrieval import cosine, normalize_text
from app.pipeline.embedding import embed_texts, embedding_model


ReferenceStage = Literal["extraction", "curator", "challenger"]

_REFERENCE_DIR = Path(__file__).parent / "reference_cases"
_REFERENCE_FILES = (
    "extraction_cases.json",
    "code_matching_cases.json",
    "code_creation_cases.json",
    "rejection_cases.json",
)
_CASE_VECTOR_CACHE: dict[str, dict[str, list[float]]] = {}


def _flatten_text(value: Any) -> str:
    """Ghép các giá trị chữ trong một case thành văn bản phục vụ truy xuất nhẹ."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return ""


def _validate_case(case: Any, *, source: str, index: int) -> dict[str, Any]:
    """Kiểm tra tối thiểu để dataset lỗi không âm thầm đi vào prompt."""
    if not isinstance(case, dict):
        raise ValueError(f"{source}[{index}] phải là object JSON.")
    missing = {"id", "stage", "input", "expected", "principle"} - set(case)
    if missing:
        raise ValueError(f"{source}[{index}] thiếu trường: {sorted(missing)}")
    if case["stage"] not in {"extraction", "curator", "challenger"}:
        raise ValueError(f"{source}[{index}] có stage không hợp lệ: {case['stage']}")
    return case


@lru_cache(maxsize=1)
def load_reference_cases() -> tuple[dict[str, Any], ...]:
    """Đọc dataset tĩnh một lần; thứ tự file và ID tạo kết quả có thể tái lập."""
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for filename in _REFERENCE_FILES:
        path = _REFERENCE_DIR / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{filename} phải chứa một JSON array.")
        for index, raw_case in enumerate(payload):
            case = _validate_case(raw_case, source=filename, index=index)
            case_id = str(case["id"])
            if case_id in seen_ids:
                raise ValueError(f"ID case bị trùng: {case_id}")
            seen_ids.add(case_id)
            cases.append(case)
    return tuple(cases)


def select_reference_cases(
    stage: ReferenceStage,
    *,
    item_name: str,
    query_texts: list[str],
    limit: int = 2,
    embedding_client: OpenAI | None = None,
) -> list[dict[str, Any]]:
    """Lấy vài án lệ gần nhất bằng cùng model embedding dùng cho codebook.

    Dataset chỉ cung cấp cách áp dụng quy tắc. ID/code trong ví dụ không bao giờ
    được dùng làm ID thật khi lưu mapping.
    """
    if limit <= 0:
        return []
    query_values = [text for text in query_texts if text.strip()] or [item_name]
    stage_cases = [case for case in load_reference_cases() if case["stage"] == stage]
    model = embedding_model(embedding_client)
    cache = _CASE_VECTOR_CACHE.setdefault(model, {})
    missing_cases = [case for case in stage_cases if str(case["id"]) not in cache]
    batch = embed_texts(
        [*query_values, *[_flatten_text(case) for case in missing_cases]],
        embedding_client,
    )
    queries = batch.vectors[: len(query_values)]
    for case, vector in zip(missing_cases, batch.vectors[len(query_values) :]):
        cache[str(case["id"])] = vector
    normalized_item = normalize_text(item_name)
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for case in stage_cases:
        case_vector = cache[str(case["id"])]
        semantic_score = max((cosine(query, case_vector) for query in queries), default=0.0)
        same_item_bonus = (
            0.08
            if normalize_text(str(case.get("item", ""))) == normalized_item
            else 0.0
        )
        ranked.append((semantic_score + same_item_bonus, str(case["id"]), case))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [case for _, _, case in ranked[:limit]]


def reference_cases_json(
    stage: ReferenceStage,
    *,
    item_name: str,
    query_texts: list[str],
    limit: int,
    embedding_client: OpenAI | None = None,
) -> str:
    """Nén án lệ liên quan vào một ngân sách ký tự cố định cho prompt."""
    cases = select_reference_cases(
        stage,
        item_name=item_name,
        query_texts=query_texts,
        limit=limit,
        embedding_client=embedding_client,
    )
    prompt_cases: list[dict[str, Any]] = []
    for case in cases:
        compact = {
            "input": case["input"],
            "expected": case["expected"],
            "principle": case["principle"],
        }
        candidate = [*prompt_cases, compact]
        encoded = json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
        if prompt_cases and len(encoded) > settings.reference_cases_max_chars:
            break
        prompt_cases = candidate
    return json.dumps(prompt_cases, ensure_ascii=False, separators=(",", ":"))
