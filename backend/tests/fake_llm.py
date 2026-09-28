"""Fake OpenAI client cho test — không gọi mạng.

Nhận trước danh sách 'responses' (chuỗi JSON hoặc Exception để mô phỏng lỗi/retry).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _Msg:
    content: str


@dataclass
class _Choice:
    message: _Msg
    finish_reason: str | None = None


@dataclass
class _Completion:
    id: str
    choices: list
    usage: object | None = None


class _Completions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        r = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        if isinstance(r, Exception):
            raise r
        if isinstance(r, dict) and "content" in r:
            usage = r.get("usage")
            usage_object = (
                type("FakeUsage", (), {"model_dump": lambda self: usage})()
                if usage is not None
                else None
            )
            return _Completion(
                id=f"fake-{self.calls}",
                choices=[_Choice(_Msg(r["content"]), r.get("finish_reason"))],
                usage=usage_object,
            )
        return _Completion(id=f"fake-{self.calls}", choices=[_Choice(_Msg(r))])


class _Chat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, responses):
        self.chat = _Chat(_Completions(responses))
