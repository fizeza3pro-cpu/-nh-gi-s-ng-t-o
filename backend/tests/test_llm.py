import pytest

from app.pipeline.llm import LLMJSONError, chat_json, extract_json
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
