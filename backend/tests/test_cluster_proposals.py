"""Cụm đề xuất chỉ để quan sát, không tự chốt mã."""

from app.pipeline.cluster_proposals import propose_clusters


def _idea(idea_id: str, vector: list[float], model: str = "semantic-v1") -> dict:
    return {
        "idea_id": idea_id,
        "response_id": f"response-{idea_id}",
        "original": f"Ý {idea_id}",
        "normalized": f"Ý chuẩn {idea_id}",
        "functional_signature": {
            "goal": "trang trí", "object_role": "vật liệu", "mechanism": "ghép nối",
        },
        "embedding": vector,
        "embedding_model": model,
    }


def test_shadow_clustering_groups_close_ideas_without_assigning_codes():
    ideas = [
        _idea("a", [1.0, 0.0]),
        _idea("b", [0.98, 0.2]),
        _idea("c", [-1.0, 0.0]),
        _idea("d", [1.0, 0.0], "semantic-v2"),
    ]
    codes = [{
        "id": "decor", "name": "Trang trí", "embedding": [1.0, 0.0],
        "embedding_model": "semantic-v1", "functional_signature": ideas[0]["functional_signature"],
        "exclusion_rules": ["Không dùng để giữ nhiệt"],
    }]
    report = propose_clusters(ideas, codes, similarity_floor=0.9)

    assert report["vectorized_ideas"] == 4
    assert report["missing_vectors"] == 0
    assert [proposal["member_count"] for proposal in report["proposals"]] == [2, 1, 1]
    pair = report["proposals"][0]
    assert {member["idea_id"] for member in pair["members"]} == {"a", "b"}
    assert pair["nearest_codes"][0]["code_id"] == "decor"
    assert all("code_id" not in member for member in pair["members"])


def test_complete_linkage_does_not_chain_two_distant_ideas():
    report = propose_clusters([
        _idea("a", [1.0, 0.0]),
        _idea("b", [0.94, 0.342]),
        _idea("c", [0.766, 0.643]),
    ], [], similarity_floor=0.9)

    assert sorted(proposal["member_count"] for proposal in report["proposals"]) == [1, 2]


def test_missing_or_cross_model_vectors_are_not_forced_into_cluster():
    ideas = [
        _idea("a", [1.0, 0.0]),
        _idea("b", [1.0, 0.0], "semantic-v2"),
        _idea("c", [float("nan"), 0.0]),
        _idea("d", []),
    ]
    report = propose_clusters(ideas, [], similarity_floor=0.9)
    assert report["vectorized_ideas"] == 2
    assert report["missing_vectors"] == 2
    assert len(report["proposals"]) == 2


def test_common_generic_verbs_do_not_join_different_goals():
    first = _idea("a", [1.0, 0.0])
    second = _idea("b", [1.0, 0.0])
    first["functional_signature"]["goal"] = "làm đồ trang trí"
    second["functional_signature"]["goal"] = "làm đồ giữ nhiệt"
    report = propose_clusters([first, second], [], similarity_floor=0.9)
    assert len(report["proposals"]) == 2
