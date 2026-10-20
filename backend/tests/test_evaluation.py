from evaluation.run import evaluate, wilson
from app.core import generate_match
from fastapi.testclient import TestClient
from app.main import app


def test_offline_evaluation_all_pass():
    report = evaluate((20261020, 20261021), tuple(range(2000, 2040)), tuple(range(3000, 3010)), tuple(range(5000, 5004)))
    assert report['passed']
    assert report['checks_total'] == 18 + 11
    for tier in ('count_change', 'interpretation'):
        assert report['detector'][tier]['labelled_shifts'] + report['detector'][tier]['control_matches'] == 10
        assert 0 <= report['detector'][tier]['precision'] <= 1
    assert [row['strength'] for row in report['strength_curve']] == [0.5, 1.0, 1.5, 2.0, 3.0]
    assert wilson(0, 0) is None and wilson(5, 10)[0] < .5 < wilson(5, 10)[1]


def test_api_health_and_match():
    client = TestClient(app)
    assert client.get('/health').json()['status'] == 'ok'
    match = client.get('/api/match').json()
    assert match['total_events'] == len(generate_match())
    assert set(match['statistics']) == {'home', 'away'}


def test_api_rejects_invalid_parameters():
    client = TestClient(app)
    assert client.get('/api/state?minute=91').status_code == 422
    assert client.get('/api/overlays?language=invalid').status_code == 422


def test_websocket_replay_protocol():
    client = TestClient(app)
    with client.websocket_connect('/ws/match?speed=0.05') as ws:
        first = ws.receive_json()
        second = ws.receive_json()
    assert first['minute'] == 1 and second['minute'] == 2
    assert 'statistics' in first and 'overlays' in first
