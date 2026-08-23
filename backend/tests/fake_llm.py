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


@dataclass
class _Completion:
    id: str
    choices: list


class _Completions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def create(self, **_kwargs):
        r = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        if isinstance(r, Exception):
            raise r
        return _Completion(id=f"fake-{self.calls}", choices=[_Choice(_Msg(r))])


class _Chat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, responses):
        self.chat = _Chat(_Completions(responses))
