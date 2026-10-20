from app.core import Event, generate_match
from app.pitch import pitch_state
from fastapi.testclient import TestClient
from app.main import app

def test_initial_pitch_has_full_lineups():
    pitch = pitch_state([], 0)
    assert len(pitch['players']) == 22
    assert len({p['player_id'] for p in pitch['players']}) == 22
    assert pitch['ball'] == {'x': 50.0, 'y': 50.0, 'source_event_id': None}
    assert all(p['position_source'] == 'illustrative_formation' for p in pitch['players'])

def test_pitch_reproducibility_bounds_and_no_future_leakage():
    events = generate_match()
    for minute in (1, 20, 67, 90):
        state = pitch_state(events, minute)
        assert state == pitch_state([e for e in events if e.minute < minute], minute)
        assert len(state['players']) == 22
        assert all(0 <= p['x'] <= 100 and 0 <= p['y'] <= 100 for p in state['players'])
        assert all(p['position_source'] in {'illustrative_formation', 'event_actor', 'event_recipient'} for p in state['players'])

def test_away_pass_keeps_evidence_separate_from_formation():
    event = Event('a', 'm', 1, 1, 0, 'away', 'away-02', 'pass', 60, 40,
                  80, 50, recipient_player_id='away-03')
    pitch = pitch_state([event], 2)
    players = {p['player_id']: p for p in pitch['players']}
    assert pitch['action']['from_x'] == 40
    assert pitch['action']['to_x'] == pitch['ball']['x'] == 20
    assert players['away-02']['x'] > players['away-09']['x']
    assert players['away-03']['x'] != pitch['ball']['x']
    assert players['away-03']['active']
    assert players['away-03']['position_source'] == 'illustrative_formation'
    assert pitch['action']['event_id'] == 'a'

def test_pitch_is_delivered_in_state_and_websocket():
    client = TestClient(app)
    assert len(client.get('/api/state?minute=67').json()['pitch']['players']) == 22
    with client.websocket_connect('/ws/match?start_minute=67&speed=0.05') as ws:
        assert len(ws.receive_json()['pitch']['players']) == 22


def test_role_lines_and_smooth_team_shape_across_complete_replay():
    events = generate_match()
    previous = None
    for minute in range(91):
        state = pitch_state(events, minute)
        players = {p['player_id']: p for p in state['players']}
        assert state['formation'] == '4-3-3'
        for team, sign in [('home', 1), ('away', -1)]:
            keeper = players[f'{team}-01']
            assert (keeper['facing_x'] - keeper['x']) * sign > 0
            assert 32 <= keeper['y'] <= 68
            assert (3 <= keeper['x'] <= 12) if team == 'home' else (88 <= keeper['x'] <= 97)
            defenders = [players[f'{team}-{n:02}'] for n in range(2, 6)]
            midfield = [players[f'{team}-{n:02}'] for n in range(6, 9)]
            attack = [players[f'{team}-{n:02}'] for n in range(9, 12)]
            assert max(p['x']*sign for p in defenders) < min(p['x']*sign for p in midfield)
            assert max(p['x']*sign for p in midfield) < min(p['x']*sign for p in attack)
        if previous:
            for p in state['players']:
                old = previous[p['player_id']]
                assert ((p['x']-old['x'])**2 + (p['y']-old['y'])**2)**.5 < 2
        previous = players


def test_keeper_cannot_be_pulled_upfield_by_random_event_coordinates():
    event = Event('a', 'm', 1, 1, 0, 'home', 'home-01', 'shot', 95, 90)
    state = pitch_state([event], 2)
    keeper = state['players'][0]
    assert keeper['x'] < 12
    assert keeper['facing_x'] > keeper['x']
    assert state['action']['from_x'] == 95
