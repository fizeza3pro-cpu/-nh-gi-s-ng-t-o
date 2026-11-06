"""Chọn ca cần phân xử cuối; giữ tên hàm cũ cho các công cụ tích hợp."""

from app.config import settings
from app.pipeline.code_retrieval import RETRIEVAL_PROFILE


def verification_reason(idea, decision, candidates) -> str | None:
    """Chỉ kiểm chứng rủi ro cụ thể; không lặp một cặp đã có bằng chứng độc lập."""
    if decision.pair_verified or (decision.reviewed_by_challenger and decision.policy_gates.get("final_adjudication_checked")):
        return None
    if decision.decision == "MATCH_EXISTING" and any(c.get("retrieval_profile") == RETRIEVAL_PROFILE for c in candidates):
        # Cờ đóng mặc định; bằng chứng Curator không được vô hiệu hóa rủi ro CREATE bên dưới.
        if (settings.curator_direct_acceptance_enabled and decision.policy_gates.get("curator_evidence_checked")
                and not idea.inferred_signature_fields):
            return None
        return "multi_vector_match_requires_semantic_check"
    entirely_inferred = set(idea.inferred_signature_fields) >= {"goal", "object_role", "mechanism"}
    if decision.decision == "MATCH_EXISTING" and entirely_inferred:
        return "fully_inferred_match"
    if decision.decision == "CREATE_NEW":
        modern = [c for c in candidates if c.get("retrieval_profile") == RETRIEVAL_PROFILE]
        if any(float((c.get("signature_similarity") or {}).get("goal") or 0) >= .7
               and float((c.get("signature_similarity") or {}).get("object_role") or 0) >= .7 for c in modern):
            return "new_code_overlaps_semantic_fields"
        if any(c.get("retrieval_profile") != RETRIEVAL_PROFILE
               and float(c.get("semantic_similarity") or 0) >= settings.auto_match_semantic_floor
               and float((c.get("signature_similarity") or {}).get("weighted") or 0)
                   >= settings.auto_match_structural_floor for c in candidates):
            return "new_code_overlaps_candidate"
        if entirely_inferred:
            return "fully_inferred_creation"
    return None



def verify_decisions(item, ideas, curator, candidates, client):
    """Điểm vào tương thích: dùng cùng Challenger cuối, không tạo tầng kiểm chứng riêng."""
    from app.pipeline.adjudication import adjudicate_decisions

    return adjudicate_decisions(item, ideas, curator, candidates, client)
