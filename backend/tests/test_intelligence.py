from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from app.claims import validate_claim
from app.core import DEFAULT_SEED, Event, generate_match, pass_difficulty, statistics
from app.dynamics import state_at, timeline
from app.experience import Profile, experience, personalized_moments
from app.languages import SUPPORTED
from app.live import LiveMatch
from app.main import app
from app.moments import detect_moments, render
from app.players import SPEED_TAG_KMH, physical, player_stats, player_tags
from app.recap import build_recap
from app.squads import CLUBS, PLAYERS

EVENTS = generate_match()


def test_clubs_and_players_are_fictional_and_complete():
    assert {c.name for c in CLUBS.values()} == {'Calderbrook FC', 'Merridge Athletic'}
    assert len(PLAYERS) == 32 and len({p.name for p in PLAYERS.values()}) == 32
    for team in ('home', 'away'):
        shirts = [p.shirt for p in PLAYERS.values() if p.team_id == team]
        assert len(set(shirts)) == 16 and PLAYERS[f'{team}-01'].position == 'GK' and PLAYERS[f'{team}-01'].shirt == 1
    body = TestClient(app).get('/api/squads').text
    assert 'North London' not in body and 'Manchester' not in body


def test_new_event_fields_are_plausible_and_leave_the_match_unchanged():
    stats = statistics(EVENTS)
    assert (stats['home']['goals'], stats['away']['goals']) == (2, 3)  # identical to generator v3
    shots = [e for e in EVENTS if e.event_type == 'shot']
    passes = [e for e in EVENTS if e.event_type == 'pass']
    assert all(35 <= e.speed_kmh <= 135 for e in shots) and all(15 <= e.speed_kmh <= 110 for e in passes)
    assert 0.15 < sum(bool(e.under_pressure) for e in passes) / len(passes) < 0.45
    short = Event('a', 'm', 1, 1, 0, 'home', 'home-02', 'pass', 30, 50, 33, 52, set_piece='throw_in')
    hard = Event('b', 'm', 2, 1, 5, 'home', 'home-06', 'pass', 50, 50, 88, 30, under_pressure=True)
    assert 1 <= pass_difficulty(short) < pass_difficulty(hard) <= 10


def test_physical_data_never_changes_after_the_fact():
    early = physical([e for e in EVENTS if e.minute < 30], DEFAULT_SEED)
    full = physical(EVENTS, DEFAULT_SEED)
    for player_id, rows in early.items():
        assert rows[:30] == full[player_id][:30]
    substituted = {e.player_id for e in EVENTS if e.event_type == 'substitution'}
    for player_id in substituted:
        assert full[player_id][-1] == (0.0, 0.0)


def test_player_stats_reconcile_with_team_statistics():
    stats = player_stats(EVENTS, DEFAULT_SEED, 90)
    team = statistics(EVENTS)
    for side in ('home', 'away'):
        own = [s for s in stats.values() if s['team_id'] == side]
        assert sum(s['goals'] for s in own) == team[side]['goals']
        assert sum(s['shots'] for s in own) == team[side]['shots']
        assert sum(s['completed_passes'] for s in own) == team[side]['completed_passes']
    assert all(s['rating'] == 0 for s in stats.values() if not s['minutes'])
    tags = player_tags(EVENTS, DEFAULT_SEED, 90)
    speed = [t for t in tags if t['kind'] == 'top_speed']
    assert speed and all(t['value'] >= SPEED_TAG_KMH for t in speed)
    assert len({t['player_id'] for t in speed}) == len(speed)  # one speed tag per player


def test_dynamics_follow_their_definitions():
    for state in timeline(EVENTS, 90):
        w, d = state['window'], state['definition']
        if state['control']['state'] == 'control':
            team = state['control']['team_id']
            assert w['pass_share'][team] >= d['control_pass_share']
            assert w['passes_per_possession'][team] >= d['control_passes_per_possession']
        elif state['control']['state'] == 'chaos':
            assert w['turnovers_per_min'] >= d['chaos_turnovers_per_min']
    assert state_at(EVENTS, 3) is None
    assert state_at(EVENTS, 40) == state_at([e for e in EVENTS if e.minute < 40], 40)  # causal


def test_goal_moments_explain_the_game_state():
    goals = [m for m in detect_moments(EVENTS, DEFAULT_SEED, 90) if m['kind'] == 'goal']
    assert [m['why'] for m in goals] == ['opener', 'equaliser', 'go_ahead', 'extends', 'pulls_back']
    assert goals[0]['facts']['assister'] == 'away-07'
    for code in SUPPORTED:
        for moment in detect_moments(EVENTS, DEFAULT_SEED, 90):
            rendered = render(moment, code)
            assert rendered['headline'] and '{' not in rendered['headline'] + rendered['body']


def test_personalization_changes_selection_not_facts():
    moments = detect_moments(EVENTS, DEFAULT_SEED, 90)
    fan = personalized_moments(moments, Profile(audience='fan'), limit=500)
    analyst = personalized_moments(moments, Profile(audience='analyst'), limit=500)
    assert {m['kind'] for m in fan} < {m['kind'] for m in analyst}
    assert 'tempo_high' not in {m['kind'] for m in fan}
    focus = personalized_moments(moments, Profile(audience='analyst', focus_player='away-10'), limit=500)
    assert all('away-10' in m['player_ids'] or m['kind'] in {'goal', 'red_card', 'hat_trick'} for m in focus)
    favourite = personalized_moments(moments, Profile(audience='fan', club='home', players=('home-10',)), limit=500)
    rhodes = [m for m in favourite if 'home-10' in m['player_ids']]
    assert rhodes and all(m['favourite_player'] for m in rhodes)
    same = {m['id']: m['facts'] for m in analyst}
    assert all(same[m['id']] == m['facts'] for m in favourite if m['id'] in same)


def test_experience_and_metric_tracker():
    view = experience(EVENTS, DEFAULT_SEED, 67, Profile(audience='fan', language='de', club='away',
                                                       focus_player='away-03', metric='xg'))
    assert view['clubs']['away']['favourite'] and view['clubs']['away']['label'] == 'Dein Verein'
    assert view['metric']['current'] == {'home': 1.18, 'away': 2.9} and 'xG' in view['metric']['statement']
    assert view['focus']['player']['goals'] == 2 and view['focus']['physical']
    with pytest.raises(ValueError):
        Profile(players=('nobody',)).validate()


@pytest.mark.parametrize('minute,title', [(45, 'Half-time'), (90, 'Full-time'), (60, 'Match so far')])
def test_recaps_are_built_from_validated_claims(minute, title):
    recap = build_recap(EVENTS, DEFAULT_SEED, minute, Profile(players=('away-03',)))
    assert recap['title'] == title and recap['text'].startswith(title)
    assert all(validate_claim(c, EVENTS) == (True, 'valid') for c in recap['claims'])
    assert recap['sections']['followed_players'][0].startswith('Pedro Valença')
    scorers = [s['player'] for s in recap['sections']['scorers']]
    assert scorers == [m['player_names'][0] for m in personalized_moments(
        detect_moments(EVENTS, DEFAULT_SEED, minute), Profile(audience='analyst'), 500)[::-1] if m['kind'] == 'goal']


def test_live_pipeline_matches_batch_analysis_exactly():
    live = LiveMatch(DEFAULT_SEED, Profile(audience='analyst'))
    messages = [m for e in EVENTS for m in live.ingest(e)] + live.finish()
    live_ids = [m['moment']['id'] for m in messages if m['type'] == 'moment']
    assert sorted(live_ids) == sorted(m['id'] for m in detect_moments(EVENTS, DEFAULT_SEED, 90))
    goal_message = next(i for i, m in enumerate(messages) if m['type'] == 'moment' and m['moment']['kind'] == 'goal')
    assert messages[goal_message - 1]['type'] == 'event' and messages[goal_message - 1]['event']['outcome'] == 'goal'


def test_live_ingestion_rejects_a_bad_event_without_corrupting_the_stream():
    live = LiveMatch(DEFAULT_SEED, Profile())
    for e in EVENTS[:50]:
        live.ingest(e)
    with pytest.raises(ValueError):
        live.ingest(EVENTS[10])  # duplicate
    with pytest.raises(ValueError):
        live.ingest(replace(EVENTS[50], x=140))
    live.ingest(EVENTS[50])  # the valid event is still accepted afterwards
    assert len(live.events) == 51


def test_ingest_api_is_guarded_and_validates(monkeypatch):
    client = TestClient(app)
    assert client.post('/api/live/sessions').status_code == 403
    monkeypatch.setenv('MATCHMIND_INGEST_TOKEN', 'test-token')
    assert client.post('/api/live/sessions', headers={'X-Ingest-Token': 'wrong'}).status_code == 401
    session = client.post('/api/live/sessions', headers={'X-Ingest-Token': 'test-token'}).json()['session_id']
    url = f'/api/live/sessions/{session}/events'
    body = [e.json() for e in EVENTS[:30]]
    ok = client.post(url, json=body, headers={'X-Ingest-Token': 'test-token'}).json()
    assert ok['accepted'] == 30 and ok['messages'][0]['type'] == 'event'
    bad = client.post(url, json=[EVENTS[30].json(), EVENTS[5].json()], headers={'X-Ingest-Token': 'test-token'})
    assert bad.status_code == 422 and bad.json()['accepted'] == 1 and 'Duplicate' in bad.json()['reason']


def test_live_websocket_streams_events_and_moments():
    client = TestClient(app)
    with client.websocket_connect('/ws/live?speed=3600&start_minute=60&club=away&language=es') as ws:
        assert ws.receive_json()['type'] == 'start'
        seen = []
        while True:
            message = ws.receive_json()
            seen.append(message)
            if message['type'] == 'moment' and message['moment']['kind'] == 'goal':
                break
    goal = seen[-1]['moment']
    assert goal['minute'] >= 60 and goal['headline'].startswith('Gol de') and goal['favourite_club']
    assert any(m['type'] == 'event' and m['event']['player_name'] for m in seen)
