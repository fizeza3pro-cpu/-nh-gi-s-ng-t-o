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




def rebuild_confirmed_members(
    code: ItemCode,
    members: list[tuple[list[float], str]],
    *,
    drift_cosine_floor: float,
    expected_model: str | None = None,
) -> bool:
    """Dựng lại từ ý đã lưu; không phụ thuộc thứ tự submit hoặc remap."""
    available = [
        (unit_vector(vector), model)
        for vector, model in members
        if model and vector
    ]
    available = [(vector, model) for vector, model in available if vector]
    if not available:
        changed = bool(code.centroid_count or code.centroid or code.centroid_sum)
        if changed:
            code.centroid = []
            code.centroid_sum = []
            code.prototype_vectors = []
            code.centroid_count = 0
            code.centroid_model = ""
            code.centroid_revision = (code.centroid_revision or 0) + 1
        return changed

    models = Counter(model for _, model in available)
    model = expected_model or code.centroid_model or sorted(models, key=lambda name: (-models[name], name))[0]
    representation_changed = bool(expected_model and code.centroid_model != expected_model)
    if representation_changed:
        code.centroid = []
        code.centroid_sum = []
        code.prototype_vectors = []
        code.centroid_count = 0
        code.centroid_model = expected_model
        code.drift_flag = False
    vectors = sorted(
        [vector for vector, candidate_model in available if candidate_model == model],
        key=tuple,
    )
    if not vectors:
        code.drift_flag = True
        if representation_changed:
            code.centroid_revision = (code.centroid_revision or 0) + 1
        return representation_changed
    if expected_model:
        code.drift_flag = False  # Đánh giá lại từ tập hiện hành; không giữ cảnh báo của biểu diễn cũ.
    dimension = len(vectors[0])
    vectors = [vector for vector in vectors if len(vector) == dimension]
    if len(vectors) != (len(members) if expected_model else len(available)):
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
        representation_changed or code.centroid_count != len(vectors)
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
