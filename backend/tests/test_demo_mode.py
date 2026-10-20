import importlib
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def demo_app(monkeypatch, tmp_path):
    """A fresh app instance configured like the public demo container."""
    static = tmp_path / 'static'
    static.mkdir()
    (static / 'index.html').write_text('<!doctype html><title>MatchMind</title>', encoding='utf-8')
    monkeypatch.setenv('MATCHMIND_ENV', 'demo')
    monkeypatch.setenv('MATCHMIND_ALLOWED_HOSTS', 'matchmind-demo.example.net')
    monkeypatch.setenv('MATCHMIND_STATIC_DIR', str(static))
    monkeypatch.setenv('MATCHMIND_REVIEW_ENABLED', 'true')
    monkeypatch.setenv('MATCHMIND_RESEARCH_ENABLED', 'true')
    monkeypatch.setenv('MATCHMIND_INGEST_TOKEN', 'secret')
    monkeypatch.setenv('MATCHMIND_FOUNDATION_DB', str(tmp_path / 'demo.sqlite3'))
    import app.main as main
    import app.foundation as foundation
    foundation.repository_at.cache_clear()
    main = importlib.reload(main)
    from app.guard import GUARD
    GUARD.cache.clear()
    GUARD.calls.clear()
    yield main.app
    for name in ('MATCHMIND_ENV', 'MATCHMIND_ALLOWED_HOSTS', 'MATCHMIND_STATIC_DIR'):
        monkeypatch.delenv(name, raising=False)
    importlib.reload(main)


def test_demo_is_read_only_and_serves_the_frontend(demo_app):
    with TestClient(demo_app, base_url='https://matchmind-demo.example.net') as client:
        assert os.environ['MATCHMIND_REVIEW_ENABLED'] == 'false'
        assert os.environ['MATCHMIND_RESEARCH_ENABLED'] == 'false' and 'MATCHMIND_INGEST_TOKEN' not in os.environ
        assert client.get('/health').json()['status'] == 'ok'
        assert 'MatchMind' in client.get('/').text and 'MatchMind' in client.get('/app').text
        assert client.post('/api/foundation/reviews', json={}).status_code in (403, 422)
        assert client.post('/api/live/sessions').status_code == 403
    with TestClient(demo_app, base_url='https://evil.example.com') as client:
        assert client.get('/health').status_code == 400


def test_demo_caches_and_limits_model_calls(demo_app):
    with TestClient(demo_app, base_url='https://matchmind-demo.example.net') as client:
        first = client.get('/api/recap/agent?minute=45', headers={'X-Forwarded-For': '203.0.113.7'})
        assert first.status_code == 200
        # The same request is served from cache and does not count against the visitor.
        for _ in range(6):
            assert client.get('/api/recap/agent?minute=45', headers={'X-Forwarded-For': '203.0.113.7'}).json() == first.json()
        statuses = [client.get(f'/api/recap/agent?minute={m}', headers={'X-Forwarded-For': '203.0.113.7'}).status_code
                    for m in (50, 55, 60, 65, 70)]
        assert statuses == [200, 200, 200, 429, 429]
        assert client.get('/api/recap/agent?minute=75', headers={'X-Forwarded-For': '198.51.100.2'}).status_code == 200


def test_production_stays_release_blocked(monkeypatch):
    from app.runtime import RuntimeConfigurationError, validate_runtime
    monkeypatch.setenv('MATCHMIND_ENV', 'production')
    with pytest.raises(RuntimeConfigurationError):
        validate_runtime()
