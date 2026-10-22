"""Cost guard for model-backed endpoints on a public demo.

Results are cached per request key (which includes the match state version, so corrections
invalidate them), and each visitor may start a limited number of new model runs per minute.
Cached answers never count against the limit. Applies only when MATCHMIND_ENV=demo.

With shared state (REDIS_URL, see shared.py) the cache and the limits are shared by every
replica; if Redis cannot be reached, each replica falls back to its own memory.
"""
from __future__ import annotations
import json
import logging
import time
from collections import OrderedDict, defaultdict, deque
from typing import Any

from . import shared

RUNS_PER_MINUTE = 4
CACHE_SECONDS = 15 * 60
CACHE_SIZE = 256
log = logging.getLogger('pitchlight.guard')


class ModelCallGuard:
    def __init__(self, runs_per_minute: int = RUNS_PER_MINUTE, cache_seconds: int = CACHE_SECONDS,
                 name: str = 'model'):
        self.runs_per_minute = runs_per_minute
        self.cache_seconds = cache_seconds
        self.name = name
        self.cache: OrderedDict[tuple, tuple[float, Any, float]] = OrderedDict()
        self.calls: dict[str, deque[float]] = defaultdict(deque)

    def cached(self, key: tuple) -> Any | None:
        r = shared.client()
        if r is not None:
            try:
                raw = r.get(shared.key('cache', self.name, *key))
                return json.loads(raw) if raw else None
            except Exception as exc:
                log.warning('shared_cache_read_failed error_type=%s', type(exc).__name__)
        hit = self.cache.get(key)
        if hit and time.monotonic() - hit[0] < hit[2]:
            self.cache.move_to_end(key)
            return hit[1]
        self.cache.pop(key, None)
        return None

    def allow(self, visitor: str) -> bool:
        r = shared.client()
        if r is not None:
            try:
                # A fixed one-minute window per visitor, counted across every replica.
                k = shared.key('rate', self.name, visitor, int(time.time() // 60))
                count = r.incr(k)
                r.expire(k, 70)
                return count <= self.runs_per_minute
            except Exception as exc:
                log.warning('shared_rate_limit_failed error_type=%s', type(exc).__name__)
        now = time.monotonic()
        window = self.calls[visitor]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.runs_per_minute:
            return False
        window.append(now)
        return True

    def store(self, key: tuple, value: Any, keep: float | None = None) -> None:
        """`keep` overrides the default lifetime, for results keyed by the match state version."""
        lifetime = keep if keep is not None else self.cache_seconds
        r = shared.client()
        if r is not None:
            try:
                r.set(shared.key('cache', self.name, *key), json.dumps(value, default=str), ex=max(1, int(lifetime)))
                return
            except Exception as exc:
                log.warning('shared_cache_write_failed error_type=%s', type(exc).__name__)
        self.cache[key] = (time.monotonic(), value, lifetime)
        self.cache.move_to_end(key)
        while len(self.cache) > CACHE_SIZE:
            self.cache.popitem(last=False)


GUARD = ModelCallGuard()


def visitor(request) -> str:
    """Client address, using the first X-Forwarded-For hop behind a managed ingress."""
    forwarded = request.headers.get('x-forwarded-for', '')
    return forwarded.split(',')[0].strip() or (request.client.host if request.client else 'unknown')
