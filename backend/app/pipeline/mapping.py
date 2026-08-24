# from pathlib import Path
# from openai import OpenAI

# from app.config import settings
# from app.pipeline.llm import chat_json
# from app.schemas import Item, MappingResult


# PROMPT_PATH = Path(__file__).parent / "prompts" / "mapping.txt"
# _TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


# def build_prompt(item: Item, raw_input: str) -> str:
#     code_list_str = "\n".join(f"- {c}" for c in item.codes)
#     return _TEMPLATE.format(
#         item_name=item.name,
#         item_description=item.description,
#         code_list=code_list_str,
#         raw_input=raw_input,
#     )


# def run_mapping(item: Item, raw_input: str, client: OpenAI) -> tuple[MappingResult, dict]:
#     prompt = build_prompt(item, raw_input)
#     data, meta = chat_json(
#         client,
#         model=settings.openai_model,
#         temperature=settings.mapping_temperature,
#         prompt=prompt,
#     )
#     result = MappingResult.model_validate(data)
#     return result, meta



from pathlib import Path
from google import genai

from app.config import settings
from app.pipeline.llm import chat_json
from app.schemas.schemas import Item, MappingResult


PROMPT_PATH = Path(__file__).parent / "prompts" / "mapping.txt"
_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


def build_prompt(item: Item, raw_input: str) -> str:
    code_list_str = "\n".join(f"- {c}" for c in item.codes)
    return _TEMPLATE.format(
        item_name=item.name,
        item_description=item.description,
        code_list=code_list_str,
        raw_input=raw_input,
    )


def run_mapping(item: Item, raw_input: str, client: genai.Client) -> tuple[MappingResult, dict]:
    prompt = build_prompt(item, raw_input)
    data, meta = chat_json(
        client,
        model=settings.llm_model,
        temperature=settings.mapping_temperature,
        prompt=prompt,
    )
    result = MappingResult.model_validate(data)
    return result, meta