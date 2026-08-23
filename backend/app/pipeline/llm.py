# """Shared LLM helper: gọi chat completion trả JSON, có retry + parse an toàn.

# Lý do tồn tại (WHY): GPT-4o thỉnh thoảng trả JSON hỏng hoặc bọc trong ```json.
# Anti-pattern E.2 trong CLAUDE.md: "Coi LLM output là JSON hợp lệ luôn" — phải có
# retry + parse-failure handling để pipeline không crash khi chấm thật.
# """
# import json
# import re
# import time
# from typing import Any

# from openai import OpenAI


# class LLMJSONError(RuntimeError):
#     """LLM không trả về JSON hợp lệ sau khi đã retry."""


# _FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


# def extract_json(content: str) -> dict[str, Any]:
#     """Trích JSON từ text LLM, kể cả khi bị bọc trong code fence hoặc lẫn chữ."""
#     content = (content or "").strip()
#     if not content:
#         raise LLMJSONError("LLM trả về nội dung rỗng.")

#     # 1. Thử parse trực tiếp.
#     try:
#         return json.loads(content)
#     except json.JSONDecodeError:
#         pass

#     # 2. Bóc code fence ```json ... ```.
#     m = _FENCE_RE.search(content)
#     if m:
#         try:
#             return json.loads(m.group(1))
#         except json.JSONDecodeError:
#             pass

#     # 3. Lấy đoạn từ dấu { đầu tiên tới } cuối cùng.
#     start = content.find("{")
#     end = content.rfind("}")
#     if start != -1 and end != -1 and end > start:
#         try:
#             return json.loads(content[start : end + 1])
#         except json.JSONDecodeError:
#             pass

#     raise LLMJSONError(f"Không parse được JSON từ LLM. Nội dung: {content[:200]}")


# def chat_json(
#     client: OpenAI,
#     *,
#     model: str,
#     temperature: float,
#     prompt: str,
#     max_retries: int = 2,
# ) -> tuple[dict[str, Any], dict[str, Any]]:
#     """Gọi chat completion (JSON mode) với retry. Trả (data, meta).

#     Retry khi: lỗi mạng/API, hoặc parse JSON thất bại. Backoff tuyến tính đơn giản.
#     """
#     last_err: Exception | None = None
#     for attempt in range(max_retries + 1):
#         try:
#             completion = client.chat.completions.create(
#                 model=model,
#                 temperature=temperature,
#                 response_format={"type": "json_object"},
#                 messages=[{"role": "user", "content": prompt}],
#             )
#             content = completion.choices[0].message.content or ""
#             data = extract_json(content)
#             meta = {
#                 "model": model,
#                 "temperature": temperature,
#                 "response_id": completion.id,
#                 "raw_response": content,
#                 "attempts": attempt + 1,
#             }
#             return data, meta
#         except Exception as err:  # noqa: BLE001 - retry mọi lỗi transient
#             last_err = err
#             if attempt < max_retries:
#                 time.sleep(0.8 * (attempt + 1))

#     raise LLMJSONError(f"Thất bại sau {max_retries + 1} lần gọi LLM: {last_err}")


"""Shared LLM helper: gọi model trả JSON, có retry + parse an toàn.

Lý do tồn tại (WHY): LLM thỉnh thoảng trả JSON hỏng hoặc bọc trong ```json.
Anti-pattern E.2 trong CLAUDE.md: "Coi LLM output là JSON hợp lệ luôn" — phải có
retry + parse-failure handling để pipeline không crash khi chấm thật.

Đổi provider (2026-08): chuyển từ OpenAI sang Google Gemini (free tier, AI Studio).
Interface chat_json() giữ nguyên chữ ký để mapping.py/scoring.py không cần sửa logic,
chỉ cần đổi loại client truyền vào (genai.Client thay vì OpenAI).
"""
import json
import re
import time
from typing import Any

from google import genai
from google.genai import types


class LLMJSONError(RuntimeError):
    """LLM không trả về JSON hợp lệ sau khi đã retry."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(content: str) -> dict[str, Any]:
    """Trích JSON từ text LLM, kể cả khi bị bọc trong code fence hoặc lẫn chữ."""
    content = (content or "").strip()
    if not content:
        raise LLMJSONError("LLM trả về nội dung rỗng.")

    # 1. Thử parse trực tiếp.
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2. Bóc code fence ```json ... ```.
    m = _FENCE_RE.search(content)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Lấy đoạn từ dấu { đầu tiên tới } cuối cùng.
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise LLMJSONError(f"Không parse được JSON từ LLM. Nội dung: {content[:200]}")


def chat_json(
    client: genai.Client,
    *,
    model: str,
    temperature: float,
    prompt: str,
    max_retries: int = 2,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Gọi Gemini (JSON mode) với retry. Trả (data, meta).

    Retry khi: lỗi mạng/API (bao gồm rate limit 429 của free tier), hoặc parse
    JSON thất bại. Backoff tuyến tính đơn giản.
    """
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            content = response.text or ""
            data = extract_json(content)
            meta = {
                "model": model,
                "temperature": temperature,
                "response_id": getattr(response, "response_id", None),
                "raw_response": content,
                "attempts": attempt + 1,
            }
            return data, meta
        except Exception as err:  # noqa: BLE001 - retry mọi lỗi transient (bao gồm 429)
            last_err = err
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))  # backoff dài hơn OpenAI vì free tier rate limit chặt hơn

    raise LLMJSONError(f"Thất bại sau {max_retries + 1} lần gọi LLM: {last_err}")
