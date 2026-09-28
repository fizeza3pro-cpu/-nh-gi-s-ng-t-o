"""Centroid chỉ là bằng chứng truy xuất; không thay thế ranh giới của mã."""

import math

from app.models.models import ItemCode
from app.pipeline.centroid import add_confirmed_member, rebuild_confirmed_members, unit_vector


def _code() -> ItemCode:
    return ItemCode(
        item_id="dua", name="Trang trí", normalized_name="trang tri",
        centroid=[], centroid_sum=[], centroid_count=0, centroid_revision=0,
        centroid_model="", drift_flag=False,
    )


def test_centroid_is_order_independent_normalized_mean():
    first = _code()
    second = _code()
    vectors = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]
    for vector in vectors:
        assert add_confirmed_member(first, vector, "model-v1", drift_cosine_floor=0.1)
    for vector in reversed(vectors):
        assert add_confirmed_member(second, vector, "model-v1", drift_cosine_floor=0.1)
    assert first.centroid_count == second.centroid_count == 3
    assert first.centroid_revision == second.centroid_revision == 3
    assert first.centroid == second.centroid
    assert math.isclose(math.sqrt(sum(value * value for value in first.centroid)), 1.0)


def test_centroid_rejects_mixed_models_and_invalid_vectors():
    code = _code()
    assert add_confirmed_member(code, [1.0, 0.0], "model-v1", drift_cosine_floor=0.7)
    assert not add_confirmed_member(code, [0.0, 1.0], "model-v2", drift_cosine_floor=0.7)
    assert code.centroid_count == 1
    assert code.drift_flag
    assert unit_vector([float("nan"), 1.0]) == []
    assert unit_vector([0.0, 0.0]) == []


def test_rebuild_uses_current_members_and_stable_prototypes():
    first = _code()
    second = _code()
    members = [([1.0, 0.0], "v1"), ([0.8, 0.6], "v1"), ([0.0, 1.0], "v1")]
    assert rebuild_confirmed_members(first, members, drift_cosine_floor=0.1)
    assert rebuild_confirmed_members(second, list(reversed(members)), drift_cosine_floor=0.1)
    assert first.centroid == second.centroid
    assert first.prototype_vectors == second.prototype_vectors
    assert first.centroid_count == 3
    assert rebuild_confirmed_members(first, members[:1], drift_cosine_floor=0.1)
    assert first.centroid_count == 1
    assert first.prototype_vectors == [[1.0, 0.0]]


def test_rebuild_never_mixes_embedding_models():
    code = _code()
    assert rebuild_confirmed_members(code, [([1.0, 0.0], "v1")], drift_cosine_floor=0.1)
    assert not rebuild_confirmed_members(code, [([0.0, 1.0], "v2")], drift_cosine_floor=0.1)
    assert code.centroid_model == "v1"
    assert code.drift_flag
