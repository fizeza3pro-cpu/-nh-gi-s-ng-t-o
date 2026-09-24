"""Lớp gọi LLM trả JSON, có retry và parse an toàn."""

import json
import re
import time
from typing import Any

from openai import OpenAI


class LLMJSONError(RuntimeError):
    """LLM không trả về JSON hợp lệ sau khi đã retry."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_DURATION_RE = re.compile(r"^(?:(?P<minutes>[0-9.]+)m)?(?:(?P<seconds>[0-9.]+)s)?$")
_CONTEXT_LIMIT_RE = re.compile(
    r"maximum context length is (?P<context>\d+) tokens.*?"
    r"requested (?P<output>\d+) output tokens.*?"
    r"prompt contains at least (?P<input>\d+) input tokens",
    re.IGNORECASE | re.DOTALL,
)
_CONTEXT_SAFETY_TOKENS = 128


def _response_format_is_unsupported(error: Exception) -> bool:
    """Nhận diện lỗi provider không hỗ trợ JSON mode để gọi lại bằng prompt thuần."""
    message = str(error).casefold()
    return "response_format" in message and any(
        marker in message
        for marker in ("not support", "unsupported", "invalid", "unknown", "not allowed")
    )


def _reasoning_effort_is_unsupported(error: Exception) -> bool:
    """Nhận diện model/provider từ chối tham số reasoning_effort."""
    message = str(error).casefold()
    return "reasoning_effort" in message and any(
        marker in message
        for marker in ("not support", "unsupported", "invalid", "unknown", "not allowed")
    )


def _reduced_max_tokens_for_context(
    error: Exception, current_max_tokens: int | None
) -> int | None:
    """Tính lại ngân sách output khi tổng input + output vượt context của model."""
    if current_max_tokens is None:
        return None
    match = _CONTEXT_LIMIT_RE.search(str(error))
    if not match:
        return None
    context_tokens = int(match.group("context"))
    input_tokens = int(match.group("input"))
    reduced = context_tokens - input_tokens - _CONTEXT_SAFETY_TOKENS
    if reduced < 256 or reduced >= current_max_tokens:
        return None
    return reduced


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


def _parse_duration(value: str | None) -> float | None:
    """Đọc Retry-After dạng giây hoặc chuỗi như 1m2.5s của Groq."""
    if not value:
        return None
    raw = value.strip().lower()
    try:
        return float(raw)
    except ValueError:
        match = _DURATION_RE.fullmatch(raw)
        if not match:
            return None
        return float(match.group("minutes") or 0) * 60 + float(match.group("seconds") or 0)


def _retry_delay_seconds(error: Exception, attempt: int) -> float:
    """Ưu tiên thời gian reset do provider trả về, tối đa 30 giây mỗi lần."""
    fallback = 0.8 * (2**attempt)
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or getattr(error, "headers", None) or {}
    retry_after = _parse_duration(headers.get("retry-after"))
    token_reset = _parse_duration(headers.get("x-ratelimit-reset-tokens"))
    requested = retry_after if retry_after is not None else token_reset
    return min(max(requested if requested is not None else fallback, fallback), 30.0)


def chat_json(
    client: OpenAI,
    *,
    model: str,
    temperature: float,
    prompt: str,
    provider: str = "",
    reasoning_effort: str | None = None,
    max_tokens: int | None = None,
    max_retries: int = 2,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Gọi chat completion ở JSON mode và trả về cặp dữ liệu, metadata."""
    last_err: Exception | None = None
    use_json_mode = True
    use_reasoning_effort = bool(reasoning_effort)
    effective_max_tokens = max_tokens
    for attempt in range(max_retries + 1):
        try:
            request = {
                "model": model,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if use_reasoning_effort:
                request["reasoning_effort"] = reasoning_effort
            if effective_max_tokens is not None:
                request["max_tokens"] = effective_max_tokens
            if use_json_mode:
                request["response_format"] = {"type": "json_object"}
            while True:
                try:
                    completion = client.chat.completions.create(**request)
                    break
                except Exception as err:  # noqa: BLE001 - fallback tương thích từng model
                    if "response_format" in request and _response_format_is_unsupported(err):
                        use_json_mode = False
                        request.pop("response_format", None)
                        continue
                    if "reasoning_effort" in request and _reasoning_effort_is_unsupported(err):
                        use_reasoning_effort = False
                        request.pop("reasoning_effort", None)
                        continue
                    reduced_max_tokens = _reduced_max_tokens_for_context(
                        err, effective_max_tokens
                    )
                    if reduced_max_tokens is not None:
                        effective_max_tokens = reduced_max_tokens
                        request["max_tokens"] = reduced_max_tokens
                        continue
                    raise
            choice = completion.choices[0]
            content = choice.message.content or ""
            finish_reason = getattr(choice, "finish_reason", None)
            try:
                data = extract_json(content)
            except LLMJSONError as err:
                if finish_reason == "length":
                    raise LLMJSONError(
                        "Phản hồi JSON bị cắt vì chạm giới hạn output token "
                        f"({effective_max_tokens or 'mặc định của provider'})."
                    ) from err
                raise
            return data, {
                "provider": provider,
                "model": model,
                "temperature": temperature,
                "response_id": completion.id,
                "raw_response": content,
                "attempts": attempt + 1,
                "json_mode": use_json_mode,
                "reasoning_effort": reasoning_effort if use_reasoning_effort else None,
                "max_tokens": effective_max_tokens,
                "configured_max_tokens": max_tokens,
                "finish_reason": finish_reason,
            }
        except Exception as err:  # noqa: BLE001 - cần retry cả lỗi mạng lẫn JSON
            last_err = err
            if attempt < max_retries:
                time.sleep(_retry_delay_seconds(err, attempt))

    raise LLMJSONError(f"Thất bại sau {max_retries + 1} lần gọi LLM: {last_err}")
