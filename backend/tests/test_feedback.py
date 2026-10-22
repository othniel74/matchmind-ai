"""'Was this useful?': counted, rate-limited, sent to telemetry; no free text accepted."""
from fastapi.testclient import TestClient

from app.main import app


def test_feedback_is_counted_and_validated():
    client = TestClient(app)
    before = client.get('/api/feedback/summary').json()['fact_checker']['useful']
    assert client.post('/api/feedback', json={'feature': 'fact_checker', 'useful': True, 'language': 'es'}).json() == {'recorded': True}
    assert client.get('/api/feedback/summary').json()['fact_checker']['useful'] == before + 1
    assert client.post('/api/feedback', json={'feature': 'anything', 'useful': True}).status_code == 422
    assert client.post('/api/feedback', json={'feature': 'ask', 'useful': 'yes'}).status_code == 422
    codes = [client.post('/api/feedback', json={'feature': 'ask', 'useful': False}).status_code for _ in range(25)]
    assert 429 in codes  # a visitor cannot flood it
