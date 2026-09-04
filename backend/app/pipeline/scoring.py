"""Scoring stage — CHỈ còn Elaboration dùng LLM.

Fluency/Flexibility/Originality được tính bằng công thức trong
compute_scores.py (dùng DBCodeStatsStore), gọi TRƯỚC hàm run_scoring()
này ở response_controller.py, rồi ghép kết quả lại.
"""
import json
from pathlib import Path
# from google import genai
from openai import OpenAI
from app.config import settings
from app.pipeline.llm import chat_json
from app.schemas.schemas import Item, PerIdeaScore, ScoringResult


PROMPT_PATH = Path(__file__).parent / "prompts" / "scoring.txt"
_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


def build_prompt(item: Item, valid_ideas: list[dict]) -> str:
    return _TEMPLATE.format(
        item_name=item.name,
        valid_ideas_json=json.dumps(valid_ideas, ensure_ascii=False, indent=2),
    )


def _elaborate_once(
    item: Item, valid_ideas: list[dict], client: OpenAI
) -> tuple[dict, dict]:
    prompt = build_prompt(item, valid_ideas)
    data, meta = chat_json(
        client,
        model=settings.llm_model,
        temperature=settings.scoring_temperature,
        prompt=prompt,
    )
    return data, meta


def _average_elaboration(runs: list[list[dict]]) -> list[dict]:
    n = min(len(r) for r in runs)
    averaged = []
    for i in range(n):
        elabs = [r[i]["elaboration"] for r in runs]
        ref = runs[0][i]
        averaged.append({**ref, "elaboration": round(sum(elabs) / len(elabs))})
    return averaged


def run_scoring(
    item: Item,
    fluency: int,
    flexibility: int,
    flexibility_codes: list[str],
    per_idea_originality: list[PerIdeaScore],
    client: OpenAI,
    runs: int | None = None,
) -> tuple[ScoringResult, dict]:
    """Nhận Fluency/Flexibility/Originality ĐÃ TÍNH SẴN (từ compute_scores.py)
    làm tham số, chỉ gọi LLM để chấm Elaboration rồi ghép kết quả."""
    if not per_idea_originality:
        return (
            ScoringResult(
                fluency=0, flexibility=0, flexibility_codes=[],
                originality=0, elaboration=0, per_idea_scores=[],
                summary_vi="Không có ý tưởng hợp lệ nào để chấm điểm. Hãy thử nghĩ thêm nhiều cách dùng khác nhau cho đồ vật.",
            ),
            {"model": settings.llm_model, "skipped": True},
        )

    n_runs = max(1, runs if runs is not None else settings.scoring_runs)
    valid_ideas_payload = [
        {"normalized": p.normalized, "code": p.code} for p in per_idea_originality
    ]

    run_payloads, metas = [], []
    for _ in range(n_runs):
        data, meta = _elaborate_once(item, valid_ideas_payload, client)
        run_payloads.append(data)
        metas.append(meta)

    elaboration_runs = [d["elaboration_scores"] for d in run_payloads]
    elaboration_scores = (
        elaboration_runs[0] if n_runs == 1 else _average_elaboration(elaboration_runs)
    )

    per_idea_scores = [
        PerIdeaScore(
            normalized=orig.normalized,
            code=orig.code,
            originality=orig.originality,
            elaboration=elab["elaboration"],
            note=elab.get("note", ""),
        )
        for orig, elab in zip(per_idea_originality, elaboration_scores)
    ]

    result = ScoringResult(
        fluency=fluency,
        flexibility=flexibility,
        flexibility_codes=flexibility_codes,
        originality=sum(p.originality for p in per_idea_scores),
        elaboration=sum(p.elaboration for p in per_idea_scores),
        per_idea_scores=per_idea_scores,
        summary_vi=run_payloads[0].get("summary_vi", ""),
    )
    meta = {
        "model": settings.llm_model,
        "temperature": settings.scoring_temperature,
        "runs": n_runs,
        "response_ids": [m.get("response_id") for m in metas],
        "note": "fluency/flexibility/originality computed via formula, not LLM",
    }
    return result, meta