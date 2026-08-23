# """Baseline 1-tầng: gộp Mapping + Scoring vào MỘT lần gọi LLM.

# Đây KHÔNG phải pipeline sản phẩm (đó là 2 tầng ở mapping.py + scoring.py). File này
# chỉ tồn tại làm baseline cho thực nghiệm ablation "2-tầng vs 1-tầng" — đóng góp kỹ
# thuật chính của dự án (CLAUDE.md Phần C.2, E.1). Không import vào luồng API chính.
# """
# from pathlib import Path
# from openai import OpenAI

# from app.config import settings
# from app.pipeline.llm import chat_json
# from app.schemas import Item, ScoringResult


# PROMPT_PATH = Path(__file__).parent / "prompts" / "single_call.txt"
# _TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


# def run_single_call(item: Item, raw_input: str, client: OpenAI) -> tuple[ScoringResult, dict]:
#     prompt = _TEMPLATE.format(
#         item_name=item.name,
#         item_description=item.description,
#         raw_input=raw_input,
#     )
#     data, meta = chat_json(
#         client,
#         model=settings.openai_model,
#         temperature=settings.scoring_temperature,
#         prompt=prompt,
#     )
#     return ScoringResult.model_validate(data), meta
"""Baseline 1-tầng: gộp Mapping + Scoring vào MỘT lần gọi LLM.

Đây KHÔNG phải pipeline sản phẩm (đó là 2 tầng ở mapping.py + scoring.py). File này
chỉ tồn tại làm baseline cho thực nghiệm ablation "2-tầng vs 1-tầng" — đóng góp kỹ
thuật chính của dự án (CLAUDE.md Phần C.2, E.1). Không import vào luồng API chính.
"""
from pathlib import Path
from google import genai

from app.config import settings
from app.pipeline.llm import chat_json
from app.schemas import Item, ScoringResult


PROMPT_PATH = Path(__file__).parent / "prompts" / "single_call.txt"
_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


def run_single_call(item: Item, raw_input: str, client: genai.Client) -> tuple[ScoringResult, dict]:
    prompt = _TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        raw_input=raw_input,
    )
    data, meta = chat_json(
        client,
        model=settings.llm_model,
        temperature=settings.scoring_temperature,
        prompt=prompt,
    )
    return ScoringResult.model_validate(data), meta