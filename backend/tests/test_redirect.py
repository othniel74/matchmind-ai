"""A retired deployment redirects every request, path and query kept, and starts no background work."""
import importlib
import sys

from fastapi.testclient import TestClient


def test_redirect_mode_sends_everything_to_the_current_address(monkeypatch):
    monkeypatch.setenv('PITCHLIGHT_REDIRECT_URL', 'https://pitchlight.example.io/')
    sys.modules.pop('app.main', None)
    main = importlib.import_module('app.main')
    try:
        with TestClient(main.app, follow_redirects=False) as client:  # lifespan runs and must not start work
            r = client.get('/app?view=analysis&speed=2')
            assert r.status_code == 301 and r.headers['location'] == 'https://pitchlight.example.io/app?view=analysis&speed=2'
            assert client.get('/mcp').headers['location'] == 'https://pitchlight.example.io/mcp'
            assert client.get('/').headers['location'] == 'https://pitchlight.example.io/'
    finally:
        monkeypatch.delenv('PITCHLIGHT_REDIRECT_URL')
        sys.modules.pop('app.main', None)
        importlib.import_module('app.main')
