import pytest
from fastapi.testclient import TestClient
from app.core import generate_match
from app.graph.analytics import passing_graph, graph_metrics, network_snapshot, compare_windows
from app.main import app


def test_graph_reproducibility():
    a = network_snapshot(generate_match(42), 'away', 50, 70)
    b = network_snapshot(generate_match(42), 'away', 50, 70)
    assert a == b


def test_graph_provenance():
    evs = generate_match(42)
    snap = network_snapshot(evs, 'away', 50, 70)
    ids = {e.event_id for e in evs if 50 <= e.minute < 70 and e.team_id == 'away' and e.event_type == 'pass' and e.outcome == 'success'}
    assert all(set(edge['event_ids']) <= ids and edge['weight'] == len(edge['event_ids']) for edge in snap['edges'])


def test_empty_graph():
    snap = network_snapshot([], 'home', 0, 10)
    assert snap['metrics']['nodes'] == 0 and snap['edges'] == []


def test_window_validation():
    with pytest.raises(ValueError):
        compare_windows(generate_match(), 'home', 10)


def test_api_graph():
    client = TestClient(app)
    r = client.get('/api/graph/network?minute=67&team=away')
    assert r.status_code == 200 and r.json()['metrics']['receiver_method'] == 'explicit_recipient'
    assert client.get('/api/graph/compare?minute=67').status_code == 200
    assert client.get('/api/graph/compare?minute=20&window=15').status_code == 422


def test_rebuild_disabled_by_default(monkeypatch):
    monkeypatch.delenv('GRAPH_REBUILD_ENABLED', raising=False)
    assert TestClient(app).post('/api/graph/rebuild').status_code == 403


def test_graph_backend_rejects_unknown():
    from app.graph.repository import BoltGraphRepository
    with pytest.raises(ValueError):
        BoltGraphRepository('unknown', 'bolt://localhost:7687')

def test_rebuild_uses_one_transaction_and_creates_recipients():
    from app.graph.repository import BoltGraphRepository
    from unittest.mock import MagicMock
    repo = object.__new__(BoltGraphRepository)
    session = MagicMock()
    transaction = session.begin_transaction.return_value.__enter__.return_value
    repo._session = lambda: session
    session.__enter__.return_value = session
    assert repo.upsert_events(generate_match()) == len(generate_match())
    queries = [call.args[0] for call in transaction.run.call_args_list]
    assert 'DETACH DELETE' in queries[0]
    assert 'FOREACH (recipient' in queries[1]
    assert all(call.kwargs.get('receiver_method') == 'explicit_recipient'
               for call in transaction.run.call_args_list[2:])
    transaction.commit.assert_called_once()

def test_rebuild_does_not_commit_partial_projection():
    from app.graph.repository import BoltGraphRepository
    from unittest.mock import MagicMock
    repo = object.__new__(BoltGraphRepository)
    session = MagicMock()
    transaction = session.begin_transaction.return_value.__enter__.return_value
    session.__enter__.return_value = session
    repo._session = lambda: session
    transaction.run.side_effect = RuntimeError('database unavailable')
    with pytest.raises(RuntimeError):
        repo.upsert_events(generate_match())
    transaction.commit.assert_not_called()
