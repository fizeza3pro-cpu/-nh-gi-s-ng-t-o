# import json
# from pathlib import Path
# from openai import OpenAI

# from app.config import settings
# from app.pipeline.llm import chat_json
# from app.schemas import Item, MappingResult, PerIdeaScore, ScoringResult


# PROMPT_PATH = Path(__file__).parent / "prompts" / "scoring.txt"
# _TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


# def valid_ideas_of(mapping: MappingResult) -> list[dict]:
#     return [
#         {"normalized": idea.normalized, "code": idea.code}
#         for idea in mapping.ideas
#         if idea.status == "VALID"
#     ]


# def build_prompt(item: Item, valid_ideas: list[dict]) -> str:
#     return _TEMPLATE.format(
#         item_name=item.name,
#         valid_ideas_json=json.dumps(valid_ideas, ensure_ascii=False, indent=2),
#     )


# def _empty_result() -> ScoringResult:
#     return ScoringResult(
#         fluency=0,
#         flexibility=0,
#         flexibility_codes=[],
#         originality=0,
#         elaboration=0,
#         per_idea_scores=[],
#         summary_vi="Không có ý tưởng hợp lệ nào để chấm điểm. Hãy thử nghĩ thêm nhiều cách dùng khác nhau cho đồ vật.",
#     )


# def _score_once(item: Item, valid_ideas: list[dict], client: OpenAI) -> tuple[ScoringResult, dict]:
#     prompt = build_prompt(item, valid_ideas)
#     data, meta = chat_json(
#         client,
#         model=settings.openai_model,
#         temperature=settings.scoring_temperature,
#         prompt=prompt,
#     )
#     return ScoringResult.model_validate(data), meta


# def _average_runs(runs: list[ScoringResult]) -> tuple[ScoringResult, list[dict]]:
#     """Trung bình per-ý qua nhiều lần chấm (giảm intra-model variance — Haase 2025).

#     Căn theo index (LLM nhận cùng danh sách nên thứ tự per_idea_scores ổn định).
#     Lấy min length để an toàn nếu một lần trả thiếu ý.
#     """
#     n = min(len(r.per_idea_scores) for r in runs)
#     per_idea: list[PerIdeaScore] = []
#     per_idea_float: list[dict] = []
#     for i in range(n):
#         origs = [r.per_idea_scores[i].originality for r in runs]
#         elabs = [r.per_idea_scores[i].elaboration for r in runs]
#         avg_o = sum(origs) / len(origs)
#         avg_e = sum(elabs) / len(elabs)
#         ref = runs[0].per_idea_scores[i]
#         per_idea.append(
#             PerIdeaScore(
#                 normalized=ref.normalized,
#                 code=ref.code,
#                 originality=round(avg_o),
#                 elaboration=round(avg_e),
#                 note=ref.note,
#             )
#         )
#         per_idea_float.append(
#             {"normalized": ref.normalized, "originality": avg_o, "elaboration": avg_e}
#         )

#     base = runs[0]
#     averaged = ScoringResult(
#         fluency=base.fluency,
#         flexibility=base.flexibility,
#         flexibility_codes=base.flexibility_codes,
#         originality=sum(p.originality for p in per_idea),
#         elaboration=sum(p.elaboration for p in per_idea),
#         per_idea_scores=per_idea,
#         summary_vi=base.summary_vi,
#     )
#     return averaged, per_idea_float


# def run_scoring(
#     item: Item, mapping: MappingResult, client: OpenAI, runs: int | None = None
# ) -> tuple[ScoringResult, dict]:
#     valid_ideas = valid_ideas_of(mapping)
#     if not valid_ideas:
#         return _empty_result(), {"model": settings.openai_model, "skipped": True}

#     n_runs = runs if runs is not None else settings.scoring_runs
#     n_runs = max(1, n_runs)

#     results: list[ScoringResult] = []
#     metas: list[dict] = []
#     for _ in range(n_runs):
#         r, m = _score_once(item, valid_ideas, client)
#         results.append(r)
#         metas.append(m)

#     if n_runs == 1:
#         meta = {**metas[0], "runs": 1}
#         return results[0], meta

#     averaged, per_idea_float = _average_runs(results)
#     meta = {
#         "model": settings.openai_model,
#         "temperature": settings.scoring_temperature,
#         "runs": n_runs,
#         "response_ids": [m.get("response_id") for m in metas],
#         "per_idea_averages": per_idea_float,
#         "raw_responses": [m.get("raw_response") for m in metas],
#     }
#     return averaged, meta


import json
from pathlib import Path
from google import genai

from app.config import settings
from app.pipeline.llm import chat_json
from app.schemas import Item, MappingResult, PerIdeaScore, ScoringResult


PROMPT_PATH = Path(__file__).parent / "prompts" / "scoring.txt"
_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


def valid_ideas_of(mapping: MappingResult) -> list[dict]:
    return [
        {"normalized": idea.normalized, "code": idea.code}
        for idea in mapping.ideas
        if idea.status == "VALID"
    ]


def build_prompt(item: Item, valid_ideas: list[dict]) -> str:
    return _TEMPLATE.format(
        item_name=item.name,
        valid_ideas_json=json.dumps(valid_ideas, ensure_ascii=False, indent=2),
    )


def _empty_result() -> ScoringResult:
    return ScoringResult(
        fluency=0,
        flexibility=0,
        flexibility_codes=[],
        originality=0,
        elaboration=0,
        per_idea_scores=[],
        summary_vi="Không có ý tưởng hợp lệ nào để chấm điểm. Hãy thử nghĩ thêm nhiều cách dùng khác nhau cho đồ vật.",
    )


def _score_once(item: Item, valid_ideas: list[dict], client: genai.Client) -> tuple[ScoringResult, dict]:
    prompt = build_prompt(item, valid_ideas)
    data, meta = chat_json(
        client,
        model=settings.llm_model,
        temperature=settings.scoring_temperature,
        prompt=prompt,
    )
    return ScoringResult.model_validate(data), meta


def _average_runs(runs: list[ScoringResult]) -> tuple[ScoringResult, list[dict]]:
    """Trung bình per-ý qua nhiều lần chấm (giảm intra-model variance — Haase 2025).

    Căn theo index (LLM nhận cùng danh sách nên thứ tự per_idea_scores ổn định).
    Lấy min length để an toàn nếu một lần trả thiếu ý.
    """
    n = min(len(r.per_idea_scores) for r in runs)
    per_idea: list[PerIdeaScore] = []
    per_idea_float: list[dict] = []
    for i in range(n):
        origs = [r.per_idea_scores[i].originality for r in runs]
        elabs = [r.per_idea_scores[i].elaboration for r in runs]
        avg_o = sum(origs) / len(origs)
        avg_e = sum(elabs) / len(elabs)
        ref = runs[0].per_idea_scores[i]
        per_idea.append(
            PerIdeaScore(
                normalized=ref.normalized,
                code=ref.code,
                originality=round(avg_o),
                elaboration=round(avg_e),
                note=ref.note,
            )
        )
        per_idea_float.append(
            {"normalized": ref.normalized, "originality": avg_o, "elaboration": avg_e}
        )

    base = runs[0]
    averaged = ScoringResult(
        fluency=base.fluency,
        flexibility=base.flexibility,
        flexibility_codes=base.flexibility_codes,
        originality=sum(p.originality for p in per_idea),
        elaboration=sum(p.elaboration for p in per_idea),
        per_idea_scores=per_idea,
        summary_vi=base.summary_vi,
    )
    return averaged, per_idea_float


def run_scoring(
    item: Item, mapping: MappingResult, client: genai.Client, runs: int | None = None
) -> tuple[ScoringResult, dict]:
    valid_ideas = valid_ideas_of(mapping)
    if not valid_ideas:
        return _empty_result(), {"model": settings.llm_model, "skipped": True}

    n_runs = runs if runs is not None else settings.scoring_runs
    n_runs = max(1, n_runs)

    results: list[ScoringResult] = []
    metas: list[dict] = []
    for _ in range(n_runs):
        r, m = _score_once(item, valid_ideas, client)
        results.append(r)
        metas.append(m)

    if n_runs == 1:
        meta = {**metas[0], "runs": 1}
        return results[0], meta

    averaged, per_idea_float = _average_runs(results)
    meta = {
        "model": settings.llm_model,
        "temperature": settings.scoring_temperature,
        "runs": n_runs,
        "response_ids": [m.get("response_id") for m in metas],
        "per_idea_averages": per_idea_float,
        "raw_responses": [m.get("raw_response") for m in metas],
    }
    return averaged, meta