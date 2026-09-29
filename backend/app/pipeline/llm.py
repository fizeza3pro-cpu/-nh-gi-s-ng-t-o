"""Lớp gọi LLM trả JSON, có retry và parse an toàn."""

import json
import hashlib
import re
import time
from typing import Any

from openai import OpenAI


class LLMJSONError(RuntimeError):
    """LLM không trả về JSON hợp lệ sau khi đã retry."""

    def __init__(self, message: str, *, metadata: dict[str, Any] | None = None):
        super().__init__(message)
        self.metadata = metadata or {}


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_DURATION_RE = re.compile(r"^(?:(?P<minutes>[0-9.]+)m)?(?:(?P<seconds>[0-9.]+)s)?$")
_CONTEXT_LIMIT_RE = re.compile(
    r"maximum context length is (?P<context>\d+) tokens.*?"
    r"requested (?P<output>\d+) output tokens.*?"
    r"prompt contains at least (?P<input>\d+) input tokens",
    re.IGNORECASE | re.DOTALL,
)
_CONTEXT_SAFETY_TOKENS = 128


def quota_exhausted(error: Exception) -> bool:
    """Nhận diện hết số dư/hạn mức; 429 đơn thuần chỉ là giới hạn tốc độ."""
    body = getattr(error, "body", None)
    message = (str(error) + " " + json.dumps(body, default=str)).casefold()
    return getattr(error, "status_code", None) == 402 or any(marker in message for marker in (
        "insufficient_quota", "insufficient_balance", "insufficientbalance", "insufficient balance",
        "insufficient credit", "credit balance", "quota exhausted",
        "exceeded your current quota", "billing hard limit", "billing_hard_limit",
        "arrearage", "accountoverdue", "account overdue", "balance is not enough",
    ))


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


def _usage_values(completion: Any) -> dict[str, int]:
    """Chuẩn hoá usage giữa các SDK/provider, kể cả reasoning token ẩn."""
    usage = getattr(completion, "usage", None)
    if usage is None:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "reasoning_tokens": 0,
            "cached_tokens": 0,
        }
    raw = usage.model_dump() if hasattr(usage, "model_dump") else usage
    raw = raw if isinstance(raw, dict) else {}
    completion_details = raw.get("completion_tokens_details") or {}
    prompt_details = raw.get("prompt_tokens_details") or {}
    return {
        "prompt_tokens": int(raw.get("prompt_tokens") or 0),
        "completion_tokens": int(raw.get("completion_tokens") or 0),
        "total_tokens": int(raw.get("total_tokens") or 0),
        "reasoning_tokens": int(completion_details.get("reasoning_tokens") or 0),
        "cached_tokens": int(prompt_details.get("cached_tokens") or 0),
    }


def aggregate_usage(metas: list[dict[str, Any]]) -> dict[str, int]:
    """Cộng usage của nhiều lượt mà không phụ thuộc cấu trúc metadata bao quanh."""
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
    }
    for meta in metas:
        usage = meta.get("usage") or {}
        for key in totals:
            totals[key] += int(usage.get(key) or 0)
    return totals


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
    stage: str = "",
    include_raw_response: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Gọi chat completion ở JSON mode và trả về cặp dữ liệu, metadata."""
    last_err: Exception | None = None
    use_json_mode = True
    use_reasoning_effort = bool(reasoning_effort)
    effective_max_tokens = max_tokens
    started_at = time.perf_counter()
    attempt_details: list[dict[str, Any]] = []
    request_fallbacks: list[str] = []
    for attempt in range(max_retries + 1):
        attempt_started_at = time.perf_counter()
        completion = None
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
                        request_fallbacks.append("response_format")
                        continue
                    if "reasoning_effort" in request and _reasoning_effort_is_unsupported(err):
                        use_reasoning_effort = False
                        request.pop("reasoning_effort", None)
                        request_fallbacks.append("reasoning_effort")
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
            attempt_meta = {
                "attempt": attempt + 1,
                "response_id": getattr(completion, "id", None),
                "latency_ms": round((time.perf_counter() - attempt_started_at) * 1000, 2),
                "finish_reason": finish_reason,
                "content_chars": len(content),
                "usage": _usage_values(completion),
            }
            attempt_details.append(attempt_meta)
            try:
                data = extract_json(content)
            except LLMJSONError as err:
                attempt_meta["status"] = "INVALID_JSON"
                if finish_reason == "length":
                    raise LLMJSONError(
                        "Phản hồi JSON bị cắt vì chạm giới hạn output token "
                        f"({effective_max_tokens or 'mặc định của provider'})."
                    ) from err
                raise
            attempt_meta["status"] = "OK"
            meta = {
                "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "stage": stage,
                "provider": provider,
                "model": model,
                "temperature": temperature,
                "response_id": completion.id,
                "attempts": attempt + 1,
                "attempt_details": attempt_details,
                "usage": aggregate_usage(attempt_details),
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "prompt_chars": len(prompt),
                "response_chars": len(content),
                "json_mode": use_json_mode,
                "reasoning_effort": reasoning_effort if use_reasoning_effort else None,
                "max_tokens": effective_max_tokens,
                "configured_max_tokens": max_tokens,
                "finish_reason": finish_reason,
                "request_fallbacks": request_fallbacks,
            }
            if include_raw_response:
                meta["raw_response"] = content
            return data, meta
        except Exception as err:  # noqa: BLE001 - cần retry cả lỗi mạng lẫn JSON
            last_err = err
            if completion is None:
                attempt_details.append(
                    {
                        "attempt": attempt + 1,
                        "latency_ms": round(
                            (time.perf_counter() - attempt_started_at) * 1000, 2
                        ),
                        "status": "REQUEST_ERROR",
                        "error_type": type(err).__name__,
                        "usage": _usage_values(None),
                    }
                )
            output_was_truncated = (
                isinstance(err, LLMJSONError)
                and "chạm giới hạn output token" in str(err)
            )
            permanent_error = quota_exhausted(err) or getattr(err, "status_code", None) in {400, 401, 403, 404, 422}
            if attempt < max_retries and not output_was_truncated and not permanent_error:
                time.sleep(_retry_delay_seconds(err, attempt))
            else:
                break

    attempts_made = len(attempt_details)
    raise LLMJSONError(
        f"Thất bại sau {attempts_made} lần gọi LLM: {last_err}",
        metadata={
            "error_type": type(last_err).__name__,
            "error_category": "QUOTA_EXHAUSTED" if quota_exhausted(last_err) else "LLM_ERROR",
            "retryable": not quota_exhausted(last_err) and getattr(last_err, "status_code", None) not in {400, 401, 403, 404, 422},
            "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "stage": stage,
            "provider": provider,
            "model": model,
            "attempts": attempts_made,
            "attempt_details": attempt_details,
            "usage": aggregate_usage(attempt_details),
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "prompt_chars": len(prompt),
            "reasoning_effort": reasoning_effort if use_reasoning_effort else None,
            "max_tokens": effective_max_tokens,
            "configured_max_tokens": max_tokens,
            "request_fallbacks": request_fallbacks,
            "failed": True,
        },
    )
