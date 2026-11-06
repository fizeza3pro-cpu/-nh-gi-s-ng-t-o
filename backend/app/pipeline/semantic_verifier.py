"""Phân xử cặp ngắn cho audit codebook nền; không gửi cả bài để tránh lẫn dòng."""
import hashlib
import json
from pathlib import Path

from app.config import settings
from app.pipeline.adjudication import grounded_evidence
from app.pipeline.llm import chat_json, LLMJSONError
from app.schemas.schemas import PairVerdict

_TEMPLATE = (Path(__file__).parent / "prompts/pair_verifier.txt").read_text(encoding="utf-8")


def verify_pair(item, original: str, code: dict, client):
    """Bằng chứng phải thuộc câu nguồn; không coi boolean model là đủ."""
    view = {key: code.get(key) for key in ("name", "description", "functional_signature", "inclusion_rules", "exclusion_rules")}
    prompt = _TEMPLATE.format(item_name=item.name, item_description=item.description, source_json=json.dumps(original, ensure_ascii=False), code_json=json.dumps(view, ensure_ascii=False))
    data, meta = chat_json(
        client, model=settings.active_challenger_model,
        temperature=settings.code_curator_temperature, prompt=prompt,
        provider=settings.llm_provider, reasoning_effort=settings.active_reasoning_effort,
        max_tokens=settings.max_tokens_for("pair_verifier", 1), max_retries=settings.llm_max_retries, stage="pair_verifier",
    )
    try:
        verdict = PairVerdict.model_validate(data)
    except ValueError as exc:
        raise LLMJSONError("Phân xử cặp sai contract.", metadata=meta) from exc
    evidence = grounded_evidence(verdict.evidence, original)
    if (verdict.source_text and verdict.source_text != original) or evidence is None:
        raise LLMJSONError("Phân xử cặp không giữ đúng câu và bằng chứng nguồn.", metadata=meta)
    verdict = verdict.model_copy(update={"source_text": original, "evidence": evidence})
    meta["source_digest"] = hashlib.sha256(original.encode()).hexdigest()
    meta["verdict"] = verdict.model_dump()
    return verdict, meta
