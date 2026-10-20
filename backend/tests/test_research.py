import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def research_on(monkeypatch):
    monkeypatch.setenv('MATCHMIND_RESEARCH_ENABLED', 'true')


def test_research_is_off_by_default(monkeypatch):
    monkeypatch.delenv('MATCHMIND_RESEARCH_ENABLED')
    from app.main import app
    assert TestClient(app).get('/api/research/statsbomb/match').status_code == 404
from app.main import app
from app.research import ROOT, analyze_statsbomb

def event(index, kind, team=779, **fields):
    return {'id': f'e{index}', 'index': index, 'period': 1, 'minute': 0, 'second': index,
            'type': {'name': kind}, 'team': {'id': team}, 'player': {'id': 10, 'name': 'A'},
            'location': [60, 40], **fields}

def test_pass_graph_uses_only_completed_explicit_recipients():
    events = [event(1, 'Pass', **{'pass': {'recipient': {'id': 11, 'name': 'B'}, 'end_location': [80, 50]}}),
              event(2, 'Pass', **{'pass': {'recipient': {'id': 11, 'name': 'B'}, 'outcome': {'name': 'Incomplete'}}}),
              event(3, 'Pass', **{'pass': {}})]
    result = analyze_statsbomb(events, 3)
    assert result['teams'][0]['passes'] == 3
    assert result['teams'][0]['completed'] == 2
    assert len(result['edges']) == 1
    assert result['edges'][0]['evidence'] == ['e1']
    assert result['edges'][0]['weight'] == 1
    assert result['events'][0]['start'] == [50, 50]

def test_shootout_and_own_goals_do_not_pollute_match_shots_or_xg():
    shot = {'outcome': {'name': 'Goal'}, 'statsbomb_xg': .4}
    events = [event(1, 'Shot', shot=shot), event(2, 'Shot', shot=shot, period=5),
              event(3, 'Own Goal Against', team=771)]
    result = analyze_statsbomb(events, 3)
    home = result['teams'][0]
    assert (home['goals'], home['shots'], home['xg'], home['shootout_goals']) == (2, 1, .4, 1)
    assert len(result['events']) == 2
    assert analyze_statsbomb(events, 0)['clock'] is None
    assert analyze_statsbomb(events, 1)['teams'][0]['shootout_goals'] == 0

def test_research_resource_allowlist():
    with TestClient(app) as client:
        assert client.get('/api/research/metrica/unknown').status_code == 404
        assert client.get('/api/research/statsbomb?event_limit=-1').status_code == 422

@pytest.mark.skipif(not (ROOT/'statsbomb/events.json').is_file(), reason='Optional local research sample')
def test_local_world_cup_final_evidence_and_result():
    events = json.loads((ROOT/'statsbomb/events.json').read_text(encoding='utf-8'))
    result = analyze_statsbomb(events, len(events))
    assert len(events) == 4407
    assert [t['goals'] for t in result['teams']] == [3, 3]
    assert [t['shootout_goals'] for t in result['teams']] == [4, 2]
    assert [t['shots'] for t in result['teams']] == [20, 10]
    assert sum(e['weight'] for e in result['edges']) == 994
    by_id = {e['id']: e for e in events}
    for edge in result['edges']:
        assert len(edge['evidence']) == edge['weight']
        for eid in edge['evidence']:
            raw = by_id[eid]
            assert 'outcome' not in raw['pass']
            assert raw['player']['id'] == edge['from']
            assert raw['pass']['recipient']['id'] == edge['to']

@pytest.mark.skipif(not (ROOT/'metrica/frames.json').is_file(), reason='Optional local research sample')
def test_metrica_event_and_tracking_synchronization():
    frames = json.loads((ROOT/'metrica/frames.json').read_text())
    events = json.loads((ROOT/'metrica/events.json').read_text())
    assert len(frames) == 3001
    assert [f['frame'] for f in frames] == list(range(1, 3002))
    for e in events:
        assert e['time'] == pytest.approx((e['start_frame'] - 1)/25, abs=.00001)
        assert len(frames[e['start_frame']-1]['player_data']) == 22
