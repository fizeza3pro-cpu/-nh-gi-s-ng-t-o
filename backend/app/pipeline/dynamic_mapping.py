"""Tầng mapping động: tách ý trước, sau đó dùng Code Curator để gán/tạo code."""

import json
import re
import unicodedata
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.pipeline.llm import chat_json
from app.schemas.schemas import CuratorResult, IdeaExtractionResult, Item

_PROMPT_DIR = Path(__file__).parent / "prompts"
_EXTRACTION_TEMPLATE = (_PROMPT_DIR / "idea_extraction.txt").read_text(encoding="utf-8")
_CURATOR_TEMPLATE = (_PROMPT_DIR / "code_curator.txt").read_text(encoding="utf-8")


def normalize_code_name(value: str) -> str:
    """Tạo khoá so sánh ổn định nhưng vẫn lưu riêng tên tiếng Việt có dấu."""
    plain = unicodedata.normalize("NFD", value.strip().lower())
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def run_idea_extraction(
    item: Item, raw_input: str, client: OpenAI
) -> tuple[IdeaExtractionResult, dict]:
    prompt = _EXTRACTION_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        raw_input=raw_input,
    )
    data, meta = chat_json(
        client,
        model=settings.llm_model,
        temperature=settings.mapping_temperature,
        prompt=prompt,
    )
    return IdeaExtractionResult.model_validate(data), meta


def run_code_curator(
    item: Item,
    ideas: IdeaExtractionResult,
    existing_codes: list[dict],
    client: OpenAI,
) -> tuple[CuratorResult, dict]:
    valid_ideas = [
        {
            "idea_index": index,
            "normalized": idea.normalized,
            "original": idea.original,
            "object_used": idea.object_used,
            "target_object_role": idea.target_object_role,
        }
        for index, idea in enumerate(ideas.ideas)
        if idea.status == "VALID" and idea.uses_target_object
    ]
    prompt = _CURATOR_TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        existing_codes_json=json.dumps(existing_codes, ensure_ascii=False, indent=2),
        ideas_json=json.dumps(valid_ideas, ensure_ascii=False, indent=2),
    )
    data, meta = chat_json(
        client,
        model=settings.code_curator_model or settings.llm_model,
        temperature=settings.code_curator_temperature,
        prompt=prompt,
    )
    return CuratorResult.model_validate(data), meta
