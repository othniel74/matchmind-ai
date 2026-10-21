"""Tactical change impact, pressing and shape: measured, in context, evidenced, never causal."""
import re

import pytest
from fastapi.testclient import TestClient

from app.core import generate_match
from app.languages import SUPPORTED
from app.tactics import (FINAL_THIRD, NOTABLE_PERCENTILE, WINDOW, change_points, impact, pressing,
                         window_metrics)
from app.main import app

CAUSAL = re.compile(r'\b(because|caused|due to|thanks to|led to|resulted in)\b', re.I)


@pytest.fixture(scope='module')
def events():
    return generate_match()


@pytest.fixture(scope='module')
def points(events):
    return change_points(events, 90)


def test_simultaneous_changes_are_grouped(points):
    assert [(p['team_id'], p['clock'] // 60, len(p['changes'])) for p in points] == [
        ('home', 59, 1), ('home', 70, 2), ('away', 70, 2), ('away', 76, 1), ('home', 87, 2)]


def test_nothing_is_compared_before_ten_minutes_have_passed(events, points):
    early = impact(events, points[0], minute=65)
    assert early['available'] is False
    late = impact(events, points[-1], minute=90)  # 87' change: no full ten minutes after it
    assert late['available'] is False


def test_window_evidence_matches_counts_and_stays_in_the_window(events):
    m = window_metrics(events, 'away', 3000, 3600)
    by_id = {e.event_id: e for e in events}
    assert m['final_third_entries']['value'] == len(m['final_third_entries']['evidence'])
    for event_id in m['final_third_entries']['evidence']:
        e = by_id[event_id]
        assert e.team_id == 'away' and 3000 <= e.minute * 60 + e.second < 3600
        assert e.end_x >= FINAL_THIRD > e.x and e.outcome == 'success'


@pytest.mark.parametrize('code', SUPPORTED)
def test_findings_are_ranked_evidenced_and_never_causal(events, points, code):
    result = impact(events, points[0], 90, code)
    assert result['available'] and result['caveat']
    for team in result['teams'].values():
        for m in team['metrics']:
            if m['notable']:
                assert m['swing_percentile'] >= NOTABLE_PERCENTILE and m['evidence_event_ids'] or m['metric'] == 'possession'
        for statement in team['statements']:
            if code == 'en':
                assert not CAUSAL.search(statement)
    assert any(team['statements'] for team in result['teams'].values())


def test_only_events_before_the_end_of_the_after_window_are_used(events, points):
    result = impact(events, points[0], 70)
    limit = points[0]['clock'] + WINDOW
    clock = {e.event_id: e.minute * 60 + e.second for e in events}
    for team in result['teams'].values():
        for m in team['metrics']:
            assert all(clock[i] < limit for i in m['evidence_event_ids'])


def test_incoming_player_and_risers_are_reported(events, points):
    result = impact(events, points[3], 90)  # Merridge 76': Tariq Benali on
    incoming = result['teams']['away']['incoming']
    assert incoming and incoming[0]['name'] == 'Tariq Benali' and incoming[0]['pass_share'] > 0


def test_pressing_and_shape_are_plausible(events):
    visible = [e for e in events if e.minute < 67]
    p = pressing(visible, 67)
    assert p['window'] == [52, 67]
    for team in p['teams'].values():
        assert team['ppda'] is None or team['ppda'] > 0
        assert 5 < team['line_height'] < 60 and 20 < team['width'] < 68 and 5 < team['compactness'] < 40


def test_tactics_api_mcp_and_ask():
    with TestClient(app) as client:
        changes = client.get('/api/tactics/changes?minute=90&language=fr').json()['changes']
        assert len(changes) == 5 and changes[0]['available'] and changes[0]['language'] == 'fr'
        assert client.get('/api/tactics/pressing?minute=67').json()['teams']['home']['line_height'] > 0
        headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
        tools = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list',
                                                           'params': {}}).json()['result']['tools']
        assert {'tactical_changes', 'pressing_and_shape'} <= {t['name'] for t in tools}
        answer = client.get('/api/ask?q=What%20changed%20after%20the%20substitution%3F&minute=90').json()
        assert answer['intent'] == 'change' and 'does not show' in answer['answer']
        press = client.get('/api/ask?q=Who%20is%20pressing%20more%3F&minute=67').json()
        assert press['intent'] == 'pressing' and 'PPDA' in press['answer']


def test_real_match_clock_extra_time_names_and_no_simulated_shape():
    # Provider events: first-half stoppage overlaps the second half's 45:00, and extra time runs past 90.
    from app.core import Event
    from app.tactics import played_time, scoreboard
    rows = [(1, 0, 'pass'), (1, 46, 'pass'), (2, 45, 'pass'), (2, 93, 'pass'), (3, 95, 'pass'), (3, 100, 'substitution'),
            (4, 112, 'pass'), (4, 121, 'pass')]
    events = [Event(f'e{i}', 'm', i * 10, minute, 0, 'home', 'home-08', kind, 60, 50, outcome='success', period=period,
                    replacement_player_id='home-14' if kind == 'substitution' else None,
                    recipient_player_id='home-09' if kind == 'pass' else None)
              for i, (period, minute, kind) in enumerate(rows)]
    timed = played_time(events)
    clocks = [e.minute * 60 + e.second for e in timed]
    assert all(a < b for a, b in zip(clocks, clocks[1:]))  # one continuous clock, no overlap
    assert clocks[2] == clocks[1] + 1  # the second half follows the first half's stoppage time
    assert clocks[-1] > 120 * 60 and all(e.period is None for e in timed)
    assert [scoreboard(e) for e in events] == ["1'", "45+2'", "46'", "90+4'", "96'", "101'", "113'", "120+2'"]
    point = change_points(timed, 200)[0]
    result = impact(timed, point, 200, names=lambda p: {'home-08': 'Out', 'home-14': 'In'}.get(p, p),
                    clubs={'home': 'Northbank', 'away': 'Southvale'}, with_shape=False)
    assert result['available'] and result['label'] == 'In on for Out'
    assert not any(m['metric'] in ('line_height', 'width', 'compactness') for m in result['teams']['home']['metrics'])
    synthetic = generate_match()
    assert played_time(synthetic) is synthetic  # synthetic streams are untouched
