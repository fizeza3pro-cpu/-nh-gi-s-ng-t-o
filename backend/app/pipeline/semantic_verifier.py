"""Phân xử cặp ngắn chỉ cho quyết định yếu; không gửi cả bài để tránh lẫn dòng."""
import hashlib
import json
from pathlib import Path

from app.config import settings
from app.pipeline.llm import chat_json, LLMJSONError
from app.schemas.schemas import PairVerdict, CuratorDecision

_TEMPLATE = (Path(__file__).parent / "prompts/pair_verifier.txt").read_text(encoding="utf-8")


def verify_pair(item, original: str, code: dict, client):
    """Bằng chứng phải thuộc câu nguồn; không coi boolean model là đủ."""
    view = {key: code.get(key) for key in ("name", "description", "functional_signature", "inclusion_rules", "exclusion_rules")}
    prompt = _TEMPLATE.format(item_name=item.name, source_json=json.dumps(original, ensure_ascii=False), code_json=json.dumps(view, ensure_ascii=False))
    data, meta = chat_json(
        client, model=settings.active_challenger_model,
        temperature=settings.code_curator_temperature, prompt=prompt,
        provider=settings.llm_provider, reasoning_effort=settings.active_reasoning_effort,
        max_tokens=768, max_retries=settings.llm_max_retries, stage="pair_verifier",
    )
    verdict = PairVerdict.model_validate(data)
    if verdict.source_text != original or not verdict.evidence.strip() or verdict.evidence.casefold() not in original.casefold():
        raise LLMJSONError("Phân xử cặp không giữ đúng câu và bằng chứng nguồn.", metadata=meta)
    meta["source_digest"] = hashlib.sha256(original.encode()).hexdigest()
    meta["verdict"] = verdict.model_dump()
    return verdict, meta


def propose_scope(item, original, code, client):
    """Đề xuất sửa mã hẹp; worker còn phải kiểm chứng mọi member trước khi áp dụng."""
    prompt = (Path(__file__).parent / "prompts/scope_expansion.txt").read_text(encoding="utf-8").format(
        item_name=item.name, source_json=json.dumps(original, ensure_ascii=False),
        code_json=json.dumps({key: code.get(key) for key in (
            "id", "name", "description", "functional_signature", "inclusion_rules", "exclusion_rules", "positive_examples")}, ensure_ascii=False))
    data, meta = chat_json(client, model=settings.active_challenger_model,
        temperature=settings.code_curator_temperature, prompt=prompt, provider=settings.llm_provider,
        reasoning_effort=settings.active_reasoning_effort, max_tokens=1536,
        max_retries=settings.llm_max_retries, stage="scope_proposal")
    decision = CuratorDecision.model_validate(data)
    if decision.source_text != original or decision.existing_code_id != code["id"]:
        raise LLMJSONError("Đề xuất scope lệch nguồn hoặc code đích.", metadata=meta)
    return decision.model_copy(update={"decision": "EXPAND_EXISTING", "code_relation": "IDEA_BROADER_THAN_CODE",
        "absorbed_code_ids": [], "reviewed_by_challenger": True,
        "existing_code_evaluations": [{"code_id": code["id"], "relation": "IDEA_BROADER_THAN_CODE"}]}), meta
