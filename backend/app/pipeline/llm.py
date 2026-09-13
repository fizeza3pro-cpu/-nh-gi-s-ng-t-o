"""Lớp gọi LLM trả JSON, có retry và parse an toàn."""

import json
import re
import time
from typing import Any

from openai import OpenAI


class LLMJSONError(RuntimeError):
    """LLM không trả về JSON hợp lệ sau khi đã retry."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(content: str) -> dict[str, Any]:
    """Trích JSON kể cả khi kết quả bị bọc trong code fence hoặc lẫn chữ."""
    content = (content or "").strip()
    if not content:
        raise LLMJSONError("LLM trả về nội dung rỗng.")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    match = _FENCE_RE.search(content)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise LLMJSONError(f"Không parse được JSON từ LLM. Nội dung: {content[:200]}")


def chat_json(
    client: OpenAI,
    *,
    model: str,
    temperature: float,
    prompt: str,
    max_retries: int = 2,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Gọi chat completion ở JSON mode và trả về cặp dữ liệu, metadata."""
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            content = completion.choices[0].message.content or ""
            return extract_json(content), {
                "model": model,
                "temperature": temperature,
                "response_id": completion.id,
                "raw_response": content,
                "attempts": attempt + 1,
            }
        except Exception as err:  # noqa: BLE001 - cần retry cả lỗi mạng lẫn JSON
            last_err = err
            if attempt < max_retries:
                time.sleep(0.8 * (attempt + 1))

    raise LLMJSONError(f"Thất bại sau {max_retries + 1} lần gọi LLM: {last_err}")
