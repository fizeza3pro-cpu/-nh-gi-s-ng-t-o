from types import SimpleNamespace

import pytest

from app.pipeline.llm import (
    LLMJSONError,
    _reduced_max_tokens_for_context,
    _retry_delay_seconds,
    chat_json,
    extract_json,
)
from tests.fake_llm import FakeClient


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}


def test_extract_embedded_json():
    assert extract_json('Đây là kết quả: {"a": 3} xong.') == {"a": 3}


def test_extract_empty_raises():
    with pytest.raises(LLMJSONError):
        extract_json("")


def test_chat_json_retries_then_succeeds():
    # Lần 1 trả rác (parse fail) → retry → lần 2 hợp lệ.
    client = FakeClient(["không phải json", '{"ok": true}'])
    data, meta = chat_json(client, model="x", temperature=0.0, prompt="p", max_retries=2)
    assert data == {"ok": True}
    assert meta["attempts"] == 2


def test_chat_json_gives_up():
    client = FakeClient(["rác", "vẫn rác", "rác nữa"])
    with pytest.raises(LLMJSONError):
        chat_json(client, model="x", temperature=0.0, prompt="p", max_retries=2)


def test_chat_json_falls_back_when_response_format_is_unsupported():
    client = FakeClient(
        [RuntimeError("response_format is unsupported"), '{"ok": true}']
    )

    data, meta = chat_json(
        client, model="byteplus-model", temperature=0.0, prompt="p", max_retries=0
    )

    assert data == {"ok": True}
    assert meta["json_mode"] is False
    assert client.chat.completions.calls == 2
    assert "response_format" in client.chat.completions.requests[0]
    assert "response_format" not in client.chat.completions.requests[1]
    assert meta["attempts"] == 2
    assert meta["attempt_details"][0]["status"] == "REQUEST_FALLBACK"
    assert meta["attempt_details"][0]["usage_known"] is False


def test_chat_json_passes_low_reasoning_to_groq_request():
    client = FakeClient(['{"ok": true}'])

    data, meta = chat_json(
        client,
        model="openai/gpt-oss-120b",
        temperature=0.0,
        prompt="prompt ngắn",
        provider="groq",
        reasoning_effort="low",
    )

    assert data == {"ok": True}
    assert client.chat.completions.requests[0]["reasoning_effort"] == "low"
    assert meta["attempts"] == 1


def test_chat_json_retries_without_reasoning_when_model_does_not_support_it():
    client = FakeClient(
        [RuntimeError("reasoning_effort is unsupported for this model"), '{"ok": true}']
    )

    data, meta = chat_json(
        client,
        model="model-without-reasoning",
        temperature=0.0,
        prompt="prompt ngắn",
        provider="cloudflare",
        reasoning_effort="low",
        max_retries=0,
    )

    assert data == {"ok": True}
    assert "reasoning_effort" in client.chat.completions.requests[0]
    assert "reasoning_effort" not in client.chat.completions.requests[1]
    assert meta["reasoning_effort"] is None


def test_chat_json_passes_cloudflare_output_limit():
    client = FakeClient(['{"ok": true}'])

    data, meta = chat_json(
        client,
        model="@cf/meta/test-model",
        temperature=0.0,
        prompt="prompt ngắn",
        provider="cloudflare",
        max_tokens=4096,
    )

    assert data == {"ok": True}
    assert client.chat.completions.requests[0]["max_tokens"] == 4096
    assert meta["max_tokens"] == 4096


def test_chat_json_records_reasoning_usage_and_latency_without_raw_response():
    client = FakeClient([
        {
            "content": '{"ok": true}',
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200,
                "prompt_tokens_details": {"cached_tokens": 20},
                "completion_tokens_details": {"reasoning_tokens": 60},
            },
        }
    ])

    _, meta = chat_json(
        client,
        model="deepseek-v4-flash-260425",
        temperature=0.0,
        prompt="p",
        provider="byteplus",
        reasoning_effort="minimal",
        stage="code_curator",
    )

    assert meta["stage"] == "code_curator"
    assert meta["usage"]["reasoning_tokens"] == 60
    assert meta["usage"]["cached_tokens"] == 20
    assert meta["latency_ms"] >= 0
    assert "raw_response" not in meta


def test_chat_json_recovers_truncation_once_with_larger_output():
    client = FakeClient([
        {"content": '{"unfinished":', "finish_reason": "length"},
        '{"ok": true}',
    ])
    data, meta = chat_json(client, model="test", temperature=0, prompt="p", max_tokens=512, max_retries=0)
    assert data == {"ok": True}
    assert client.chat.completions.calls == 2
    assert client.chat.completions.requests[1]["max_tokens"] > 512
    assert meta["request_fallbacks"] == ["increase_output_after_truncation"]


def test_chat_json_reduces_output_when_context_would_overflow():
    error = RuntimeError(
        "This model's maximum context length is 24000 tokens. However, you "
        "requested 8192 output tokens and your prompt contains at least 15809 "
        "input tokens, for a total of at least 24001 tokens."
    )
    client = FakeClient([error, '{"ok": true}'])

    data, meta = chat_json(
        client,
        model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        temperature=0.0,
        prompt="prompt dài",
        provider="cloudflare",
        max_tokens=8192,
        max_retries=0,
    )

    assert data == {"ok": True}
    assert client.chat.completions.calls == 2
    assert client.chat.completions.requests[0]["max_tokens"] == 8192
    assert client.chat.completions.requests[1]["max_tokens"] == 8063
    assert meta["configured_max_tokens"] == 8192
    assert meta["max_tokens"] == 8063


def test_context_limit_is_not_reduced_below_safe_json_budget():
    error = RuntimeError(
        "maximum context length is 24000 tokens; requested 8192 output tokens; "
        "prompt contains at least 23800 input tokens"
    )

    assert _reduced_max_tokens_for_context(error, 8192) is None


def test_retry_delay_uses_provider_headers_and_caps_long_waits():
    short = RuntimeError("429")
    short.response = SimpleNamespace(headers={"retry-after": "2.5"})
    long = RuntimeError("429")
    long.response = SimpleNamespace(headers={"x-ratelimit-reset-tokens": "1m2s"})

    assert _retry_delay_seconds(short, 0) == 2.5
    assert _retry_delay_seconds(long, 1) == 30.0


def test_byteplus_deepseek_thinking_is_explicit_and_other_providers_unchanged(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "byteplus_thinking", "disabled")
    client = FakeClient(['{"ok":true}'])
    _, meta = chat_json(client, model="deepseek-v4-1-flash-261017", provider="byteplus",
                        temperature=0, prompt="p", reasoning_effort="high")
    request = client.chat.completions.requests[0]
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert request["reasoning_effort"] == "minimal" and meta["thinking_type"] == "disabled"
    other = FakeClient(['{"ok":true}'])
    chat_json(other, model="other", provider="groq", temperature=0, prompt="p", reasoning_effort="low")
    assert "extra_body" not in other.chat.completions.requests[0]
    assert other.chat.completions.requests[0]["reasoning_effort"] == "low"


def test_fallback_and_retry_request_count_matches_provider_calls(monkeypatch):
    from app.pipeline.llm import collect_llm_calls, aggregate_usage
    monkeypatch.setattr("app.pipeline.llm.time.sleep", lambda seconds: None)
    client = FakeClient([RuntimeError("response_format unsupported"), RuntimeError("network timeout"),
                         {"content": '{"ok":true}', "usage": {"total_tokens": 50}}])
    _, meta = chat_json(client, model="test", temperature=0, prompt="p", max_retries=1, stage="code_curator")
    calls = collect_llm_calls({"first": meta, "copy": meta})
    assert len(calls) == meta["attempts"] == client.chat.completions.calls == 3
    assert sum(not c["usage_known"] for c in calls) == 2
    assert aggregate_usage(calls)["total_tokens"] == 50
