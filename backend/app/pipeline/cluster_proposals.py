"""Gom ý chưa có mã để kiểm toán; không tự gắn mã hoặc thay đổi điểm."""

from __future__ import annotations

import hashlib
import math

from app.pipeline.code_retrieval import cosine, normalize_text, signature_similarity
from app.pipeline.centroid import unit_vector


def _vector(values: list, model: str) -> list[float]:
    """Bỏ vector cũ/hỏng mà không làm hỏng toàn bộ báo cáo."""
    if not model or not isinstance(values, list):
        return []
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return []
    return unit_vector(numbers)


def _shared_goal(left: dict, right: dict) -> bool:
    """Cổng thận trọng cho cụm gợi ý: hai mục đích phải có ít nhất một từ chung."""
    generic = {"lam", "dung", "su", "de", "tao", "thanh", "cho", "co", "the", "vat", "do", "bang"}
    def terms(idea: dict) -> set[str]:
        goal = (idea.get("functional_signature") or {}).get("goal", "")
        return set(normalize_text(goal.replace("đ", "d").replace("Đ", "d")).split()) - generic

    first = terms(left)
    second = terms(right)
    return bool(first & second)


def _nearest_codes(members: list[dict], centroid: list[float], model: str, codes: list[dict]) -> list[dict]:
    """So cụm với anchor và centroid cùng model; chỉ trả bằng chứng retrieval."""
    ranked = []
    for code in codes:
        vectors = []
        if code.get("embedding_model") == model:
            vectors.append(_vector(code.get("embedding") or [], model))
        if code.get("centroid_model") == model and not code.get("drift_flag"):
            vectors.extend(
                _vector(vector, model)
                for vector in [code.get("centroid") or [], *(code.get("prototype_vectors") or [])]
            )
        similarities = [cosine(centroid, vector) for vector in vectors if len(vector) == len(centroid)]
        if not similarities:
            continue
        semantic = max(0.0, *similarities)
        structural = math.fsum(
            signature_similarity(member.get("functional_signature") or {}, code.get("functional_signature") or {})["weighted"]
            for member in members
        ) / len(members)
        ranked.append({
            "code_id": code["id"],
            "name": code["name"],
            "retrieval_score": round(0.75 * semantic + 0.25 * structural, 6),
            "semantic_similarity": round(semantic, 6),
            "structural_similarity": round(structural, 6),
            "exclusion_rules": (code.get("exclusion_rules") or [])[:3],
        })
    return sorted(ranked, key=lambda row: (-row["retrieval_score"], row["code_id"]))[:2]


def propose_clusters(ideas: list[dict], codes: list[dict], *, similarity_floor: float) -> dict:
    """Complete-linkage thận trọng; ngưỡng chỉ gom đề xuất, KHÔNG quyết định MATCH."""
    valid = []
    missing_vectors = 0
    for idea in ideas:
        vector = _vector(idea.get("embedding") or [], idea.get("embedding_model") or "")
        if not vector:
            missing_vectors += 1
            continue
        valid.append({**idea, "vector": vector})
    valid.sort(key=lambda row: row["idea_id"])

    similarities: dict[tuple[int, int], float] = {}
    for left in range(len(valid)):
        for right in range(left + 1, len(valid)):
            a, b = valid[left], valid[right]
            if (
                a["embedding_model"] != b["embedding_model"]
                or len(a["vector"]) != len(b["vector"])
                or not _shared_goal(a, b)
            ):
                continue
            score = cosine(a["vector"], b["vector"])
            if score >= similarity_floor:
                similarities[(left, right)] = score

    groups = {index: {index} for index in range(len(valid))}
    owner = {index: index for index in range(len(valid))}
    for (left, right), _ in sorted(
        similarities.items(), key=lambda pair: (-pair[1], pair[0])
    ):
        first, second = owner[left], owner[right]
        if first == second:
            continue
        # Không nối hai cụm chỉ nhờ một chuỗi các cặp gần nhau.
        if not all(
            (min(a, b), max(a, b)) in similarities
            for a in groups[first] for b in groups[second]
        ):
            continue
        groups[first].update(groups.pop(second))
        for index in groups[first]:
            owner[index] = first

    proposals = []
    for indices in groups.values():
        members = [valid[index] for index in sorted(indices)]
        dimensions = len(members[0]["vector"])
        centroid = unit_vector([
            math.fsum(member["vector"][axis] for member in members)
            for axis in range(dimensions)
        ])
        model = members[0]["embedding_model"]
        nearest = _nearest_codes(members, centroid, model, codes) if centroid else []
        pair_scores = [
            cosine(left["vector"], right["vector"])
            for position, left in enumerate(members)
            for right in members[position + 1:]
        ]
        member_ids = [member["idea_id"] for member in members]
        proposals.append({
            "proposal_id": hashlib.sha256("|".join(member_ids).encode("utf-8")).hexdigest()[:16],
            "embedding_model": model,
            "member_count": len(members),
            "members": [{
                "idea_id": member["idea_id"],
                "response_id": member["response_id"],
                "original": member["original"],
                "normalized": member["normalized"],
                "functional_signature": member.get("functional_signature") or {},
            } for member in members],
            "min_pair_similarity": round(min(pair_scores), 6) if pair_scores else None,
            "max_centroid_distance": round(
                max(1 - cosine(member["vector"], centroid) for member in members), 6
            ) if centroid else None,
            "nearest_codes": nearest,
            "top_two_margin": round(
                nearest[0]["retrieval_score"] - nearest[1]["retrieval_score"], 6
            ) if len(nearest) > 1 else None,
        })
    proposals.sort(key=lambda row: (-row["member_count"], row["proposal_id"]))
    return {"vectorized_ideas": len(valid), "missing_vectors": missing_vectors, "proposals": proposals}
