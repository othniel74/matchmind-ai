from dataclasses import replace
import pytest
from app.core import Event, generate_match, statistics, validate_event_stream
from app.graph.analytics import network_snapshot
from app.store import EventStore, replay_events
from fastapi.testclient import TestClient
from app.main import app

def test_score_is_derived_only_from_goals():
    events = [Event('a', 'm', 1, 1, 0, 'home', 'home-01', 'shot', 80, 50, outcome='goal'),
              Event('b', 'm', 2, 1, 15, 'away', 'away-01', 'shot', 80, 50, outcome='saved')]
    assert statistics(events)['home']['goals'] == 1
    assert statistics(events)['away']['goals'] == 0
    assert statistics(events[:0])['home']['goals'] == 0

def test_generated_pass_recipients_and_terminal_pass():
    events = generate_match()
    assert all(e.recipient_player_id for e in events if e.event_type == 'pass' and e.outcome == 'success')
    event = Event('p', 'm', 1, 89, 59, 'home', 'home-01', 'pass', 50, 50,
                  60, 50, recipient_player_id='home-02')
    snapshot = network_snapshot([event], 'home', 80, 90)
    assert snapshot['edges'] == [{'source': 'home-01', 'target': 'home-02', 'weight': 1, 'event_ids': ['p']}]
    with pytest.raises(ValueError, match='recipient'):
        validate_event_stream([replace(event, recipient_player_id='away-02')])

def test_store_survives_reopen_rejects_conflicts_and_isolates_seeds(tmp_path, monkeypatch):
    path = str(tmp_path / 'events.sqlite3')
    store = EventStore(path)
    events = generate_match(1)
    assert store.save('one', events)
    assert not store.save('one', events)
    assert EventStore(path).load('one') == events
    with pytest.raises(ValueError, match='different events'):
        store.save('one', generate_match(2))
    assert store.load('one') == events
    monkeypatch.setenv('MATCHMIND_EVENT_DB', path)
    assert replay_events(1) == events
    assert replay_events(2) != events
    assert replay_events(1) == events

def test_runtime_does_not_claim_live_inference(monkeypatch):
    monkeypatch.delenv('AZURE_AI_PROJECT_ENDPOINT', raising=False)
    response = TestClient(app).get('/api/runtime').json()
    assert response['status'] == 'fallback'
    assert response['live_inference_verified'] is False

def test_websocket_resumes_with_complete_state():
    client = TestClient(app)
    with client.websocket_connect('/ws/match?start_minute=89&speed=0.05') as socket:
        frame = socket.receive_json()
        assert frame['minute'] == 89
        expected = sum(e.minute < 89 for e in generate_match())
        assert sum(team['events'] for team in frame['statistics'].values()) == expected
        assert socket.receive_json()['minute'] == 90

@pytest.mark.parametrize('query', ['speed=nan', 'seed=no', 'start_minute=0'])
def test_invalid_websocket_parameters_close_cleanly(query):
    from starlette.websockets import WebSocketDisconnect
    with TestClient(app).websocket_connect('/ws/match?' + query) as socket:
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 1008
