"""Thống kê vector thành viên để truy xuất, không tự đổi quyết định gắn mã."""

from __future__ import annotations

import math
from collections import Counter

from app.models.models import ItemCode


def unit_vector(values: list[float]) -> list[float]:
    """Chỉ chấp nhận vector hữu hạn có độ dài khác không."""
    if not values or not all(math.isfinite(value) for value in values):
        return []
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else []


def add_confirmed_member(
    code: ItemCode,
    vector: list[float],
    model: str,
    *,
    drift_cosine_floor: float,
) -> bool:
    """Cộng đúng trọng số từng ý; từ chối trộn model hoặc chiều vector."""
    normalized = unit_vector(vector)
    if not normalized or not model:
        return False
    previous_sum = code.centroid_sum or []
    if code.centroid_count and (
        code.centroid_model != model or len(previous_sum) != len(normalized)
    ):
        code.drift_flag = True
        return False
    if not code.centroid_count:
        previous_sum = [0.0] * len(normalized)
    old_centroid = code.centroid or []
    if old_centroid and len(old_centroid) == len(normalized):
        member_similarity = sum(a * b for a, b in zip(old_centroid, normalized))
        if member_similarity < drift_cosine_floor:
            code.drift_flag = True
    next_sum = [left + right for left, right in zip(previous_sum, normalized)]
    next_centroid = unit_vector(next_sum)
    if not next_centroid:
        return False
    if old_centroid and len(old_centroid) == len(next_centroid):
        similarity = sum(a * b for a, b in zip(old_centroid, next_centroid))
        if similarity < drift_cosine_floor:
            code.drift_flag = True
    code.centroid_sum = next_sum
    code.centroid = next_centroid
    code.centroid_count = (code.centroid_count or 0) + 1
    code.centroid_revision = (code.centroid_revision or 0) + 1
    code.centroid_model = model
    return True


def rebuild_confirmed_members(
    code: ItemCode,
    members: list[tuple[list[float], str]],
    *,
    drift_cosine_floor: float,
) -> bool:
    """Dựng lại từ ý đã lưu; không phụ thuộc thứ tự submit hoặc remap."""
    available = [
        (unit_vector(vector), model)
        for vector, model in members
        if model and vector
    ]
    available = [(vector, model) for vector, model in available if vector]
    if not available:
        changed = bool(code.centroid_count)
        if changed:
            code.centroid = []
            code.centroid_sum = []
            code.prototype_vectors = []
            code.centroid_count = 0
            code.centroid_model = ""
            code.centroid_revision = (code.centroid_revision or 0) + 1
        return changed

    models = Counter(model for _, model in available)
    model = code.centroid_model or sorted(models, key=lambda name: (-models[name], name))[0]
    vectors = sorted(
        [vector for vector, candidate_model in available if candidate_model == model],
        key=tuple,
    )
    if not vectors:
        code.drift_flag = True
        return False
    dimension = len(vectors[0])
    vectors = [vector for vector in vectors if len(vector) == dimension]
    if len(vectors) != len(available):
        code.drift_flag = True  # Không trộn model hoặc chiều vector.
    vector_sum = [math.fsum(vector[index] for vector in vectors) for index in range(dimension)]
    centroid = unit_vector(vector_sum)
    if not centroid:
        code.drift_flag = True
        return False
    previous = code.centroid or []
    if previous and len(previous) == dimension:
        if sum(a * b for a, b in zip(previous, centroid)) < drift_cosine_floor:
            code.drift_flag = True
    if any(sum(a * b for a, b in zip(vector, centroid)) < drift_cosine_floor for vector in vectors):
        code.drift_flag = True

    # Một prototype gần tâm và tối đa hai ý xa nhất với các prototype đã chọn.
    prototypes = [max(vectors, key=lambda vector: (sum(a * b for a, b in zip(vector, centroid)), vector))]
    remaining = [vector for vector in vectors if vector != prototypes[0]]
    while remaining and len(prototypes) < 3:
        selected = min(
            remaining,
            key=lambda vector: (
                max(sum(a * b for a, b in zip(vector, prototype)) for prototype in prototypes),
                vector,
            ),
        )
        prototypes.append(selected)
        remaining = [vector for vector in remaining if vector != selected]

    changed = (
        code.centroid_count != len(vectors)
        or code.centroid_model != model
        or code.centroid_sum != vector_sum
        or code.prototype_vectors != prototypes
    )
    if changed:
        code.centroid = centroid
        code.centroid_sum = vector_sum
        code.prototype_vectors = prototypes
        code.centroid_count = len(vectors)
        code.centroid_model = model
        code.centroid_revision = (code.centroid_revision or 0) + 1
    return changed
