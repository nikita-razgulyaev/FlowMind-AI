"""Простой in-memory rate limiter (скользящее окно). Для нескольких инстансов нужен общий стор (Redis)."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 20000:      # защита от разрастания словаря
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                self._hits.pop(k, None)
        return True

    def check(self, key: str, message: str = "Слишком много запросов, попробуйте позже"):
        if not self.allow(key):
            raise HTTPException(429, detail={"code": "rate_limited", "message": message})


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# лимитеры для авторизации
login_limiter = RateLimiter(limit=10, window_seconds=300)
register_limiter = RateLimiter(limit=10, window_seconds=3600)
email_limiter = RateLimiter(limit=5, window_seconds=3600)
ai_chat_limiter = RateLimiter(limit=20, window_seconds=60)
telegram_chat_limiter = RateLimiter(limit=20, window_seconds=60)
