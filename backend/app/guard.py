"""Cost guard for model-backed endpoints on a public demo.

Results are cached per request key (which includes the match state version, so corrections
invalidate them), and each visitor may start a limited number of new model runs per minute.
Cached answers never count against the limit. Applies only when MATCHMIND_ENV=demo.
"""
from __future__ import annotations
import time
from collections import OrderedDict, defaultdict, deque
from typing import Any

RUNS_PER_MINUTE = 4
CACHE_SECONDS = 15 * 60
CACHE_SIZE = 256


class ModelCallGuard:
    def __init__(self, runs_per_minute: int = RUNS_PER_MINUTE, cache_seconds: int = CACHE_SECONDS):
        self.runs_per_minute = runs_per_minute
        self.cache_seconds = cache_seconds
        self.cache: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
        self.calls: dict[str, deque[float]] = defaultdict(deque)

    def cached(self, key: tuple) -> Any | None:
        hit = self.cache.get(key)
        if hit and time.monotonic() - hit[0] < self.cache_seconds:
            self.cache.move_to_end(key)
            return hit[1]
        self.cache.pop(key, None)
        return None

    def allow(self, visitor: str) -> bool:
        now = time.monotonic()
        window = self.calls[visitor]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.runs_per_minute:
            return False
        window.append(now)
        return True

    def store(self, key: tuple, value: Any) -> None:
        self.cache[key] = (time.monotonic(), value)
        self.cache.move_to_end(key)
        while len(self.cache) > CACHE_SIZE:
            self.cache.popitem(last=False)


GUARD = ModelCallGuard()


def visitor(request) -> str:
    """Client address, using the first X-Forwarded-For hop behind a managed ingress."""
    forwarded = request.headers.get('x-forwarded-for', '')
    return forwarded.split(',')[0].strip() or (request.client.host if request.client else 'unknown')
