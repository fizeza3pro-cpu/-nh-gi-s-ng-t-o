"""Đối chiếu căn cứ và tính mới theo lô nhỏ, độc lập với lý do của Curator."""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.pipeline.llm import LLMJSONError, chat_json
from app.pipeline.code_retrieval import RETRIEVAL_PROFILE


class CodeComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code_id: str
    relation: Literal["SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE", "DIFFERENT", "UNCERTAIN"]
    reason: str


class DecisionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idea_index: int
    source_text: str
    grounded: bool
    evidence: str
    reason: str
    comparisons: list[CodeComparison]


class DecisionChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checks: list[DecisionCheck]


def verification_reason(idea, decision, candidates) -> str | None:
    """Chỉ kiểm chứng rủi ro cụ thể; không lặp một cặp đã có bằng chứng độc lập."""
    if decision.pair_verified:
        return None
    if decision.decision == "MATCH_EXISTING" and any(c.get("retrieval_profile") == RETRIEVAL_PROFILE for c in candidates):
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
    """Chốt chọn lọc các ca có rủi ro; CREATE rõ ràng không phải gọi LLM lần hai."""
    from app.schemas.schemas import CuratorResult

    selected, triggers = [], {}
    for decision in curator.decisions:
        idea = ideas.ideas[decision.idea_index]
        reason = verification_reason(idea, decision, candidates.get(decision.idea_index, []))
        if reason:
            selected.append(decision)
            triggers[decision.idea_index] = reason
    if not selected:
        return curator, {"skipped": True, "reason": "no_verification_risk"}

    replacements = {}
    runs = []
    for offset in range(0, len(selected), settings.mapping_batch_size):
        batch = selected[offset:offset + settings.mapping_batch_size]
        cases, offered = [], {}
        for decision in batch:
            idea = ideas.ideas[decision.idea_index]
            nearest = list(candidates.get(decision.idea_index, []))
            # Giữ code đang chọn dù hạng thấp; không tăng kích thước toàn prompt Curator.
            chosen = [c for c in nearest if c.get("id") == decision.existing_code_id]
            shortlist = {c["id"]: c for c in [*nearest[:3], *chosen]}
            offered[decision.idea_index] = shortlist
            cases.append({
                "idea_index": decision.idea_index, "original": idea.original,
                "interpreted_function": idea.functional_signature.model_dump(),
                "proposed_category": {"name": decision.code_name,
                                      "function": decision.functional_signature.model_dump()},
                "candidates": [{k: c.get(k) for k in (
                    "id", "name", "description", "functional_signature", "inclusion_rules", "exclusion_rules"
                )} for c in shortlist.values()],
            })
        prompt = (Path(__file__).parent / "prompts/decision_verifier.txt").read_text(encoding="utf-8").format(
            cases_json=json.dumps({"item": item.name, "description": item.description, "cases": cases}, ensure_ascii=False)
        )
        meta = {}
        try:
            data, meta = chat_json(
                client, model=settings.active_challenger_model, temperature=0,
                prompt=prompt, provider=settings.llm_provider,
                reasoning_effort=settings.active_reasoning_effort,
                max_tokens=settings.max_tokens_for("code_challenger", len(batch)), max_retries=0,
                stage="decision_verifier",
            )
            checks = DecisionChecks.model_validate(data).checks
            if len(checks) != len(batch) or {c.idea_index for c in checks} != {d.idea_index for d in batch}:
                raise ValueError("Thiếu, trùng hoặc sai index đối chiếu.")
            by_index = {c.idea_index: c for c in checks}
            for decision in batch:
                check = by_index[decision.idea_index]
                original = ideas.ideas[decision.idea_index].original
                if check.source_text != original or not check.evidence.strip() or check.evidence not in original or not check.reason.strip():
                    raise ValueError("Đối chiếu không giữ căn cứ câu gốc.")
                ids = [c.code_id for c in check.comparisons]
                if len(ids) != len(set(ids)) or set(ids) != set(offered[decision.idea_index]) or any(not c.reason.strip() for c in check.comparisons):
                    raise ValueError("Đối chiếu thiếu hoặc sai code ứng viên.")
            # Chỉ áp dụng sau khi toàn lô qua kiểm tra contract.
            for decision in batch:
                check = by_index[decision.idea_index]
                matches = [c for c in check.comparisons if c.relation in {"SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE"}]
                ambiguous = any(c.relation == "UNCERTAIN" for c in check.comparisons)
                update = {"challenge_reason": check.reason,
                          "policy_gates": {**decision.policy_gates, "semantic_grounding_checked": check.grounded},
                          "existing_code_evaluations": [{**c.model_dump(), "source": "DECISION_VERIFIER",
                              "verdict": "MATCH" if c in matches else "NO_MATCH", "goal_match": c in matches,
                              "role_match": c in matches, "excluded_by": "", "evidence": check.evidence}
                              for c in check.comparisons]}
                if not check.grounded or ambiguous or len(matches) > 1 or (decision.decision == "MATCH_EXISTING" and not matches):
                    update.update(decision="UNCERTAIN", code_relation="UNCERTAIN", existing_code_id=None,
                                  pair_verified=False, reason="Cần đối chiếu chức năng: " + check.reason)
                elif matches:
                    match = matches[0]
                    update.update(decision="MATCH_EXISTING", code_relation=match.relation,
                                  existing_code_id=match.code_id, code_name=offered[decision.idea_index][match.code_id]["name"],
                                  pair_verified=True, reason=match.reason, proposal_group="")
                replacements[decision.idea_index] = decision.model_copy(update=update)
            runs.append({**meta, "checks": [c.model_dump() for c in checks],
                         "offered_code_ids": {str(i): list(values) for i, values in offered.items()}})
        except (LLMJSONError, ValueError) as exc:
            runs.append({**(getattr(exc, "metadata", None) or meta), "failed": True, "error_type": type(exc).__name__})
            for decision in batch:
                replacements[decision.idea_index] = decision.model_copy(update={
                    "decision": "UNCERTAIN", "code_relation": "UNCERTAIN", "existing_code_id": None,
                    "pair_verified": False, "reason": "Chưa hoàn tất đối chiếu căn cứ và phạm vi code.",
                })
    return CuratorResult(decisions=[replacements.get(d.idea_index, d) for d in curator.decisions]), {"runs": runs, "triggers": triggers}
