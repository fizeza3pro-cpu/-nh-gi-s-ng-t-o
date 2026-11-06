"""Phân xử cuối một lần sau Curator; backend kiểm tra căn cứ từng ý độc lập."""
from collections import Counter
from pathlib import Path
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.pipeline.code_retrieval import select_diverse_candidates
from app.pipeline.decision_verifier import verification_reason
from app.pipeline.llm import LLMJSONError, chat_json
from app.schemas.schemas import CuratorDecision, CuratorResult


class CodeComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code_id: str
    relation: Literal["SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE", "IDEA_BROADER_THAN_CODE", "DIFFERENT", "UNCERTAIN"]
    goal_match: bool = False
    role_match: bool = False
    # Chỉ trích quy tắc thật; không cho tự đặt điều kiện loại mới trong phần giải thích.
    excluded_by: str = ""
    competes_for_assignment: bool = True
    reason: str


class FinalDecision(CuratorDecision):
    source_text: str = ""
    grounded: bool
    # Câu ngắn được để trống; backend dùng chính câu gốc (xem grounded_evidence).
    evidence: str = ""
    comparisons: list[CodeComparison] = []
    uncertainty_kind: Literal["", "SEMANTIC_AMBIGUITY", "CODEBOOK_CONFLICT", "MISSING_CANDIDATE"] = ""


SHORT_SOURCE_WORDS = 8


def _unresolved(source, reason, kind):
    """Giữ ý hợp lệ và căn cứ cũ; phân biệt lỗi kỹ thuật, lỗi contract và bất định ngữ nghĩa."""
    return source.model_copy(update={
        "decision": "UNCERTAIN", "code_relation": "UNCERTAIN", "existing_code_id": None,
        "pair_verified": False, "reviewed_by_challenger": False, "reason": reason,
        "policy_gates": {**source.policy_gates, "final_adjudication_checked": False,
                         "technical_error": kind == "TECHNICAL_ERROR",
                         "contract_error": kind == "CONTRACT_ERROR",
                         "codebook_conflict": kind == "CODEBOOK_CONFLICT",
                         "missing_candidate": kind == "MISSING_CANDIDATE"},
    })


def _plain(value: str) -> str:
    """Chuẩn hoá nhẹ để so trích dẫn: không phân biệt hoa thường, dấu câu, khoảng trắng."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).split())


def grounded_evidence(evidence: str, original: str) -> str | None:
    """Backend quyết định trích dẫn; không nhận câu diễn giải hoặc đoạn bịa làm căn cứ.

    - Đoạn nằm trong câu gốc (sau chuẩn hoá): giữ nguyên đoạn đó.
    - Đoạn bao trùm câu gốc (model chép kèm diễn giải, ví dụ "dùng làm vật trang trí"
      với câu "trang trí"): dùng chính câu gốc, phần thêm không được coi là căn cứ.
    - Bỏ trống với câu ngắn: cả câu gốc là căn cứ.
    """
    source, quote = _plain(original), _plain(evidence)
    if not source:
        return None
    if quote and quote in source:
        return " ".join(evidence.split())
    if quote and source in quote:
        return original
    if not quote and len(source.split()) <= SHORT_SOURCE_WORDS:
        return original
    return None


def _validate_decision(value, source, idea, offered, *, provenance="FINAL_ADJUDICATOR"):
    """Kiểm tra định danh/căn cứ; phán đoán chức năng vẫn là kết luận của LLM."""
    from app.pipeline.dynamic_mapping import _has_reusable_scope, _hydrate_curator_decision, coerce_index

    if isinstance(value, dict) and coerce_index(value.get("idea_index")) is not None:
        value = {**value, "idea_index": coerce_index(value.get("idea_index"))}
    row = FinalDecision.model_validate(value)
    if row.idea_index != source.idea_index or (row.source_text and row.source_text != idea.original):
        raise ValueError("Sai index hoặc câu gốc của ý đang phân xử.")
    evidence = grounded_evidence(row.evidence, idea.original)
    if evidence is None or not row.reason.strip():
        raise ValueError("Thiếu trích dẫn nguyên văn hoặc lý do phân xử.")
    row = row.model_copy(update={"evidence": evidence})
    # Các mã khác biệt rõ chỉ khai ID, không lặp lời giải thích và cờ false.
    comparisons = [*row.comparisons, *[CodeComparison(code_id=code_id, relation="DIFFERENT",
        reason="Mô hình xác nhận khác chức năng.") for code_id in row.different_code_ids]]
    # IDEA_BROADER nghĩa là cùng mục đích và vai trò nhưng mã quá hẹp. Nhãn này đi kèm cả hai cờ false
    # là tự mâu thuẫn (model dùng nó cho nghĩa "có liên quan"); chính model đã khẳng định khác chức năng.
    relabeled = [comparison.code_id for comparison in comparisons
                 if comparison.relation == "IDEA_BROADER_THAN_CODE"
                 and not comparison.goal_match and not comparison.role_match]
    comparisons = [comparison.model_copy(update={"relation": "DIFFERENT"})
                   if comparison.code_id in relabeled else comparison for comparison in comparisons]
    compared = [comparison.code_id for comparison in comparisons]
    if len(compared) != len(set(compared)) or set(compared) != set(offered):
        raise ValueError("Thiếu, trùng hoặc sai code ứng viên được giao.")
    for comparison in comparisons:
        if not comparison.reason.strip():
            raise ValueError("Thiếu lý do đối chiếu code.")
        if comparison.excluded_by and comparison.excluded_by not in (offered[comparison.code_id].get("exclusion_rules") or []):
            raise ValueError("Viện dẫn quy tắc loại trừ không có trong định nghĩa code.")

    matches = [comparison for comparison in comparisons
               if comparison.relation in {"SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE"}
               and comparison.goal_match and comparison.role_match and not comparison.excluded_by]
    competing = [comparison for comparison in comparisons
                 if comparison.relation == "UNCERTAIN" and (comparison.competes_for_assignment
                                                           or (comparison.goal_match and comparison.role_match))]
    evaluations = [{**comparison.model_dump(), "source": provenance,
                    "verdict": "MATCH" if comparison in matches else "UNCERTAIN" if comparison.relation == "UNCERTAIN" else "NO_MATCH",
                    "evidence": row.evidence,
                    **({"relabeled_from": "IDEA_BROADER_THAN_CODE"} if comparison.code_id in relabeled else {})}
                   for comparison in comparisons]
    update = {
        "pair_verified": False, "reviewed_by_challenger": True,
        "policy_gates": {"final_adjudication_checked": True, "semantic_grounding_checked": row.grounded,
                         **({"broader_relabeled_different": True} if relabeled else {})},
        "existing_code_evaluations": evaluations,
        "compared_code_ids": list(offered), "nearest_code_ids": list(offered),
        "retrieval_candidates": source.retrieval_candidates,
    }
    if len(matches) > 1 and row.grounded:
        result = _unresolved(source, "Nhiều mã cùng bao phủ công dụng; cần xử lý ranh giới codebook: "
                             + ", ".join(comparison.code_id for comparison in matches), "CODEBOOK_CONFLICT")
        return result.model_copy(update={"existing_code_evaluations": evaluations}), "CODEBOOK_CONFLICT"
    if not row.grounded or competing or row.decision == "UNCERTAIN":
        kind = row.uncertainty_kind or "SEMANTIC_AMBIGUITY"
        result = _unresolved(source, row.reason, kind)
        return result.model_copy(update={"existing_code_evaluations": evaluations}), kind
    if row.decision == "MATCH_EXISTING":
        if row.existing_code_id not in offered:
            raise ValueError("MATCH sai mã đích hoặc quan hệ.")
        if len(matches) != 1 or matches[0].code_id != row.existing_code_id:
            raise ValueError("MATCH mâu thuẫn với đối chiếu chức năng của chính quyết định.")
        # Quan hệ đích chỉ có một nguồn: comparison. Đọc tương thích output cũ
        # nhưng không bắt SAME_CATEGORY và IDEA_NARROWER phải bằng nhau hai lần.
        row = row.model_copy(update={"code_relation": matches[0].relation})
        update.update(pair_verified=True, code_name=offered[row.existing_code_id]["name"])
    elif row.decision == "CREATE_NEW":
        if matches or any(comparison.relation == "IDEA_BROADER_THAN_CODE" for comparison in comparisons):
            raise ValueError("CREATE_NEW khi đã có mã bao phủ hoặc cùng họ cần sửa phạm vi.")
        if row.existing_code_id is not None or row.absorbed_code_ids:
            raise ValueError("CREATE_NEW phải khác chức năng và không có mã đích/gộp.")
        row = row.model_copy(update={"code_relation": "DIFFERENT"})
    elif row.decision == "EXPAND_EXISTING":
        target = next((comparison for comparison in comparisons if comparison.code_id == row.existing_code_id), None)
        if target is None or target.relation != "IDEA_BROADER_THAN_CODE":
            raise ValueError("EXPAND sai mã đích hoặc quan hệ mở rộng.")
        row = row.model_copy(update={"code_relation": target.relation})
        if not target.goal_match or not target.role_match or matches:
            raise ValueError("EXPAND chưa chứng minh cùng họ chức năng hoặc đã có mã bao phủ.")
        if not set(row.absorbed_code_ids) <= (set(offered) - {row.existing_code_id}):
            raise ValueError("Mã gộp nằm ngoài ứng viên hoặc trùng mã đích.")
        if any(comparison.relation != "IDEA_BROADER_THAN_CODE" or not comparison.goal_match or not comparison.role_match
               for comparison in comparisons if comparison.code_id in row.absorbed_code_ids):
            raise ValueError("EXPAND chưa có căn cứ cùng họ và quan hệ cho mã bị hấp thụ.")
    else:
        raise ValueError("Phân xử cuối chỉ được MATCH/CREATE/EXPAND/UNCERTAIN.")
    if row.decision == "MATCH_EXISTING" and row.absorbed_code_ids:
        raise ValueError("MATCH không được tự gộp mã.")
    result = _hydrate_curator_decision(CuratorDecision.model_validate(row.model_dump()), idea)
    if row.decision in {"CREATE_NEW", "EXPAND_EXISTING"} and not _has_reusable_scope(result, source_text=idea.original):
        raise ValueError("Phạm vi mã mới/mở rộng thiếu chữ ký, ranh giới hoặc hai biến thể tái sử dụng.")
    return result.model_copy(update=update), "ACCEPTED"


def adjudicate_decisions(item, ideas, curator, candidates, client):
    """Một tầng xét lại lựa chọn; chỉ retry một lần cho từng ý sai contract."""
    from app.pipeline.dynamic_mapping import _has_reusable_scope
    selected, triggers, direct = [], {}, {}
    for source in curator.decisions:
        if source.policy_gates.get("goal_grounded_in_source") is False:
            continue
        reason = verification_reason(ideas.ideas[source.idea_index], source, candidates.get(source.idea_index, []))
        if source.decision in {"UNCERTAIN", "EXPAND_EXISTING", "OUT_OF_CODEBOOK", "INVALID"}:
            reason = "review_unresolved_or_scope"
        if source.decision == "CREATE_NEW" and not _has_reusable_scope(source, source_text=ideas.ideas[source.idea_index].original):
            reason = "proposal_boundaries_incomplete"
        if (not reason and settings.curator_direct_acceptance_enabled
                and source.policy_gates.get("curator_evidence_checked")
                and source.decision in {"MATCH_EXISTING", "CREATE_NEW"}):
            direct[source.idea_index] = source.model_copy(update={
                "pair_verified": source.decision == "MATCH_EXISTING",
                "policy_gates": {**source.policy_gates, "direct_acceptance_checked": True},
            })
        if reason:
            selected.append(source)
            triggers[source.idea_index] = reason
    if not selected:
        return CuratorResult(decisions=[direct.get(s.idea_index, s) for s in curator.decisions]), {
            "skipped": True, "reason": "no_reviewable_decision", "strategy": "final_adjudication_v2",
            "direct_indices": sorted(direct)}

    replacements, runs, batches, batch = dict(direct), [], [], []
    output_cap = settings.max_tokens_for("code_challenger")
    # Chia lô theo ngân sách ước lượng; không bỏ mã cạnh tranh để ép output vừa trần token.
    candidate_limit = 24
    estimated = 256
    for source in selected:
        estimate = _output_estimate(source, min(candidate_limit, len(candidates.get(source.idea_index, []))))
        if batch and (len(batch) >= settings.mapping_batch_size or estimated + estimate > output_cap):
            batches.append(batch)
            batch, estimated = [], 256
        batch.append(source)
        estimated += estimate
    if batch:
        batches.append(batch)
    for batch in batches:
        offered, cases, rejected = {}, {}, {}
        for source in batch:
            index = source.idea_index
            pool = candidates.get(index, [])
            nearest = select_diverse_candidates(pool, min(candidate_limit, len(pool)), required_ids=[source.existing_code_id])
            offered[index] = {code["id"]: code for code in nearest}
            cases[index] = {
                "idea_index": index, "original": ideas.ideas[index].original,
                "interpreted_function": ideas.ideas[index].functional_signature.model_dump(),
                "adjudicator_decision": source.decision, "adjudicator_reason": source.reason,
                # Căn cứ Curator chỉ được chuyển tiếp khi backend đã kiểm tra; căn cứ lỗi dễ bị chép lại.
                # Đối chiếu lấy từ bản backend đã kiểm tra (BROADER tự mâu thuẫn đã đổi thành DIFFERENT),
                # chỉ giữ mã đích/cạnh tranh để không đưa nhãn sai của Curator sang Challenger.
                **({"curator_evidence": source.evidence, "curator_comparisons": [
                    {key: row.get(key) for key in ("code_id", "relation", "goal_match", "role_match", "reason")}
                    for row in source.existing_code_evaluations
                    if row.get("source") == "CURATOR" and row.get("relation") != "DIFFERENT"]}
                   if source.policy_gates.get("curator_evidence_checked") else {}),
                "review_question": _review_question(triggers[index]),
                "proposed_code": {key: source.model_dump().get(key) for key in (
                    "existing_code_id", "code_name", "code_description", "functional_signature",
                    "inclusion_rules", "exclusion_rules", "scope_variants")},
                "nearest_codes": [{key: code.get(key) for key in (
                    "id", "name", "description", "functional_signature", "inclusion_rules", "exclusion_rules")}
                    for code in nearest],
            }

        def request(sources, *, retry=False, errors=None):
            from app.pipeline.dynamic_mapping import _shared_candidate_payload, coerce_index, restore_code_aliases
            payload = [dict(cases[source.idea_index], **({"contract_error": errors[source.idea_index],
                "rejected_output": rejected.get(source.idea_index)} if retry else {}))
                       for source in sources]
            alias_map: dict[str, str] = {}
            prompt = (Path(__file__).parent / "prompts/code_challenger.txt").read_text(encoding="utf-8").format(
                item_name=item.name, item_description=item.description,
                codebook_is_empty=str(not any(offered.values())).lower(),
                challenger_cases_json=_shared_candidate_payload(payload, key="cases", alias_map=alias_map),
            )
            # Chia trước khi gọi, không fan-out một lỗi API thành nhiều request.
            if len(prompt) > settings.mapping_prompt_char_budget and len(sources) > 1:
                middle = len(sources) // 2
                return {**request(sources[:middle], retry=retry, errors=errors),
                        **request(sources[middle:], retry=retry, errors=errors)}
            if (len(prompt) > settings.mapping_prompt_char_budget or
                    256 + sum(_output_estimate(s, len(offered[s.idea_index])) for s in sources) > output_cap):
                for source in sources:
                    replacements[source.idea_index] = _unresolved(source,
                        "Ngữ cảnh phân xử vượt ngân sách request; cần điều chỉnh trước khi gọi lại.", "TECHNICAL_ERROR")
                runs.append({"failed": True, "outcome": "TECHNICAL_ERROR", "error_type": "RequestBudgetExceeded",
                             "offered_code_ids": {str(s.idea_index): list(offered[s.idea_index]) for s in sources}})
                return {}
            metadata = {}
            try:
                data, metadata = chat_json(client, model=settings.active_challenger_model, temperature=0,
                    prompt=prompt, provider=settings.llm_provider, reasoning_effort=settings.active_reasoning_effort,
                    max_tokens=output_cap, max_retries=0,
                    stage="code_challenger_retry_contract" if retry else "code_challenger")
                values = restore_code_aliases(data.get("decisions"), alias_map)
                if not isinstance(values, list):
                    raise ValueError("Thiếu danh sách decisions.")
            except (LLMJSONError, ValueError) as exc:
                runs.append({**(getattr(exc, "metadata", None) or metadata), "failed": True,
                    "outcome": "TECHNICAL_ERROR", "error_type": type(exc).__name__, "error": str(exc)[:800],
                    "offered_code_ids": {str(source.idea_index): list(offered[source.idea_index]) for source in sources}})
                for source in sources:
                    replacements[source.idea_index] = _unresolved(source,
                        "Chưa hoàn tất phân xử do lỗi kỹ thuật; chưa có kết luận ngữ nghĩa.", "TECHNICAL_ERROR")
                return {}

            # Một hàng hỏng không làm mất kết quả của các ý khác trong cùng lô.
            index_of = lambda value: coerce_index(value.get("idea_index")) if isinstance(value, dict) else None
            counts = Counter(index_of(value) for value in values if index_of(value) is not None)
            checks, invalid = [], {}
            for source in sources:
                index = source.idea_index
                try:
                    if counts[index] != 1:
                        raise ValueError("Thiếu hoặc trùng idea_index trong kết quả phân xử.")
                    value = next(value for value in values if index_of(value) == index)
                    rejected[index] = value
                    result, outcome = _validate_decision(value, source, ideas.ideas[index], offered[index])
                    replacements[index] = result
                    checks.append({"idea_index": index, "outcome": outcome, "decision": result.model_dump(),
                                   "evidence": value.get("evidence"), "comparisons": value.get("comparisons")})
                except ValueError as exc:
                    invalid[index] = str(exc)[:800]
                    # Sai contract là lỗi định dạng có tính tất định: không lên lịch phục hồi kỹ thuật.
                    replacements[index] = _unresolved(source, "Kết quả phân xử sai contract: " + invalid[index], "CONTRACT_ERROR")
            runs.append({**metadata, "checks": checks, "contract_errors": invalid,
                "rejected_decisions": [value for value in values if index_of(value) in invalid],
                # Lưu output thô khi sai contract để debug được mà không bật lưu toàn bộ phản hồi.
                **({"raw_decisions": values} if invalid else {}),
                "offered_code_ids": {str(source.idea_index): list(offered[source.idea_index]) for source in sources},
                "unexpected_indices": sorted(set(counts) - {source.idea_index for source in sources}),
                "failed": bool(invalid), "retry": retry})
            return invalid

        invalid = request(batch)
        # Gộp các ý sai contract vào một lượt sửa: catalog mã chỉ gửi lại một lần;
        # mỗi ý vẫn chỉ được sửa tối đa một lần và kết quả hợp lệ khác được giữ nguyên.
        failed_sources = [source for source in batch if source.idea_index in invalid]
        if failed_sources:
            request(failed_sources, retry=True, errors=invalid)
    return CuratorResult(decisions=[replacements.get(source.idea_index, source) for source in curator.decisions]), {
        "strategy": "final_adjudication_v2", "runs": runs, "triggers": triggers, "direct_indices": sorted(direct),
        "failed": any(decision.policy_gates.get("technical_error") or decision.policy_gates.get("contract_error")
                      for decision in replacements.values()),
    }


def _output_estimate(source, count):
    """Ước lượng theo output đo thực tế với mã ngắn C01 (~300-700 token/ý); CREATE/EXPAND thêm định nghĩa."""
    return (650 if source.decision in {"CREATE_NEW", "EXPAND_EXISTING", "UNCERTAIN", "OUT_OF_CODEBOOK"}
            else 300) + 8 * count


def _review_question(reason):
    """Chuyển tín hiệu backend thành nhiệm vụ phân xử cụ thể."""
    return {
        "new_code_overlaps_semantic_fields": "Đề xuất CREATE có bị mã cùng họ bao phủ hoặc chỉ cần mở rộng không?",
        "new_code_overlaps_candidate": "Phân biệt CREATE với mã ứng viên gần nhất theo phạm vi thật.",
        "proposal_boundaries_incomplete": "Hoàn thiện phạm vi nhóm tái sử dụng mà không tự thêm công dụng.",
        "fully_inferred_match": "Cách hiểu suy ra có được câu gốc và ngữ cảnh đồ vật hỗ trợ không?",
        "fully_inferred_creation": "Công dụng đề xuất có căn cứ hay được suy diễn thêm?",
        "review_unresolved_or_scope": "Giải quyết điểm chưa rõ/phạm vi trong lý do Curator; kiểm tra mã đích và đối thủ.",
    }.get(reason, "Kiểm tra căn cứ và phạm vi lựa chọn Curator; chỉ đổi quyết định khi có lý do cụ thể.")
