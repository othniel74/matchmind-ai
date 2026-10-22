"""Shared state for running more than one replica (optional: set REDIS_URL).

Without REDIS_URL everything stays in process memory, exactly as on a single replica. With it:
- one replica leads the Event Hubs feed (a lease that lapses if its holder stops renewing it), and
  the others follow, serving their viewers from what the leader relays;
- the model-call cache, the per-visitor limits and the kickoff locks are shared, so a recap written
  by one replica is reused by all, and a limit holds whichever replica a visitor reaches.

If Redis is unreachable, callers fall back to their in-memory behaviour: the demo keeps working,
each replica on its own. The connection string is a secret; it is never logged.
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import uuid
from typing import Any

log = logging.getLogger('pitchlight.shared')
PREFIX = 'pitchlight:'
REPLICA = os.getenv('CONTAINER_APP_REPLICA_NAME') or uuid.uuid4().hex[:12]
_sync: Any = None
_async_factory: Any = None


def enabled() -> bool:
    return bool(os.getenv('REDIS_URL')) or _sync is not None


def use(sync_client: Any, async_factory: Any) -> None:
    """Tests inject an in-memory Redis (fakeredis); None/None returns to process memory."""
    global _sync, _async_factory
    _sync, _async_factory = sync_client, async_factory


def client() -> Any:
    """The shared synchronous client, or None when state is per-process."""
    global _sync
    if _sync is None and os.getenv('REDIS_URL'):
        import redis
        _sync = redis.Redis.from_url(os.environ['REDIS_URL'], decode_responses=True, socket_timeout=3,
                                     socket_connect_timeout=3, health_check_interval=30)
    return _sync


def async_client() -> Any:
    if _async_factory is not None:
        return _async_factory()
    import redis.asyncio as aioredis
    return aioredis.Redis.from_url(os.environ['REDIS_URL'], decode_responses=True, socket_timeout=5,
                                   socket_connect_timeout=5, health_check_interval=30)


def key(*parts: Any) -> str:
    """A namespaced key; structured parts are hashed so keys stay short and safe."""
    tail = ':'.join(str(p) for p in parts)
    if len(tail) > 120 or any(c.isspace() for c in tail):
        tail = hashlib.sha256(json.dumps(parts, default=str, ensure_ascii=False).encode()).hexdigest()
    return PREFIX + tail


def claim(name: str, seconds: int) -> bool | None:
    """Take a short lock shared by every replica. True: taken; False: held elsewhere; None: no Redis."""
    r = client()
    if r is None:
        return None
    try:
        return bool(r.set(key('lock', name), REPLICA, nx=True, ex=seconds))
    except Exception as exc:
        log.warning('shared_claim_failed error_type=%s', type(exc).__name__)
        return None


def release(name: str) -> None:
    r = client()
    if r is not None:
        try:
            r.delete(key('lock', name))
        except Exception:
            pass


def status() -> dict[str, Any]:
    if not enabled():
        return {'shared_state': 'memory'}
    try:
        client().ping()
        return {'shared_state': 'redis', 'replica': REPLICA}
    except Exception as exc:
        return {'shared_state': 'redis_unreachable', 'error': type(exc).__name__, 'replica': REPLICA}
