"""Kiểm tra hạn mức tài khoản khác lỗi tốc độ và giới hạn từng phản hồi."""

import pytest

from app.pipeline.llm import LLMJSONError, chat_json, quota_exhausted
from app.controllers.admin_controller import _has_quota_failure
from tests.fake_llm import FakeClient


@pytest.mark.parametrize("message", ["insufficient_quota", "AccountOverdue", "insufficient balance"])
def test_quota_stops_retry_and_preserves_safe_category(message):
    client = FakeClient([RuntimeError(message)])
    with pytest.raises(LLMJSONError) as failure:
        chat_json(client, model="test", temperature=0, prompt="test", max_retries=2)
    assert client.chat.completions.calls == 1
    assert failure.value.metadata["retryable"] is False
    assert _has_quota_failure({"verifier": {"llm_failures": [failure.value.metadata]}})


@pytest.mark.parametrize("message", ["Rate limit reached: tokens per minute", "maximum context length exceeded", "output token limit"])
def test_transient_or_output_limit_is_not_account_quota(message):
    assert not quota_exhausted(RuntimeError(message))


def test_payment_required_is_quota_error():
    error = RuntimeError("Payment required")
    error.status_code = 402
    assert quota_exhausted(error)
