"""Giới hạn request trong một tiến trình; không tin header IP do client tự gửi."""

import math
import threading
import time
from collections import OrderedDict

from fastapi import HTTPException, Request

from app.config import settings


class RequestLimiter:
    """Cửa sổ cố định, bộ nhớ có giới hạn và đồng bộ giữa các thread."""

    def __init__(self, max_keys: int = 10000):
        self.max_keys = max_keys
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def check(self, key: tuple[str, str], limit: int, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self.lock:
            start, count = self.entries.get(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            if count >= limit:
                raise HTTPException(status_code=429, detail="Quá nhiều yêu cầu. Vui lòng chờ rồi thử lại.",
                                    headers={"Retry-After": str(max(1, math.ceil(60 - (now - start))))})
            self.entries[key] = (start, count + 1)
            self.entries.move_to_end(key)
            while len(self.entries) > self.max_keys:
                self.entries.popitem(last=False)


limiter = RequestLimiter()


def limit_login(request: Request) -> None:
    if settings.rate_limit_enabled:
        limiter.check(("login", request.client.host if request.client else "unknown"), settings.login_requests_per_minute)


def limit_public_write(request: Request) -> None:
    if settings.rate_limit_enabled:
        limiter.check(("public", request.client.host if request.client else "unknown"), settings.public_requests_per_minute)
