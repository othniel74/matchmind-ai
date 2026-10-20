"""Keeps the graph database's copy of the match knowledge graph current.

The canonical record is the event log; the in-process NetworkX graph is rebuilt from it and
the database projection is a replayable copy of that graph, refreshed whenever the source's
state version changes (for example after a correction). Without GRAPH_URI the product runs
on NetworkX alone and says so.
"""
from __future__ import annotations
import logging
import os
import threading
import time
from functools import lru_cache
from typing import Any

FULL_MATCH = 90
RETRY_SECONDS = 30
log = logging.getLogger('matchmind.graph')
_lock = threading.Lock()
_status: dict[str, Any] = {'status': 'disabled'}


def enabled() -> bool:
    return bool(os.getenv('GRAPH_URI'))


@lru_cache(maxsize=1)
def repository():
    """One driver per process; the neo4j driver pools connections and is thread-safe."""
    from .config import repository_from_env
    return repository_from_env()


def ensure(seed: int = 20261020) -> dict[str, Any]:
    """Project the full-match knowledge graph if the database is behind the source."""
    global _status
    if not enabled():
        return {'status': 'disabled', 'reason': 'GRAPH_URI is not set; NetworkX only'}
    from ..knowledge import match_graph, summary
    g, _, context = match_graph(seed, FULL_MATCH)
    with _lock:
        if _status.get('context') == context and _status.get('status') == 'ok':
            return _status
        if _status.get('status') == 'unavailable' and time.monotonic() - _status['checked_at'] < RETRY_SECONDS:
            return _status  # do not make every request wait on a database that is down
        try:
            repo = repository()
            start = time.perf_counter()
            written = repo.project_knowledge(g)
            stored = repo.kg_summary(context['match_id'])
            _status = {'status': 'ok', 'backend': repo.backend, 'context': context, 'written': written,
                       'counts_match': stored == summary(g), 'stored': stored,
                       'projection_ms': int((time.perf_counter() - start) * 1000)}
        except Exception as exc:  # the database is optional: report it, never fail the request
            log.warning('graph_projection_failed error_type=%s', type(exc).__name__)
            _status = {'status': 'unavailable', 'reason': type(exc).__name__, 'context': None,
                       'checked_at': time.monotonic()}
        return _status


def ready(seed: int = 20261020) -> Any:
    """The repository when the database holds the current source, otherwise None."""
    return repository() if enabled() and ensure(seed).get('status') == 'ok' else None


def project_at_startup(attempts: int = 20, delay: float = 3.0) -> None:
    """A sidecar database may start after the app; retry for about a minute."""
    global _status
    for _ in range(attempts):
        with _lock:
            _status = {'status': 'starting'}
        if ensure().get('status') == 'ok':
            log.info('graph_projection_ready')
            return
        time.sleep(delay)
