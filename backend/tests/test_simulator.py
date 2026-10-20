from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from app.core import (Event, SENDING_OFF, SHIFT_Z_THRESHOLD, Scenario, detect_insights, generate_match,
                      possession_seconds, scenario_for, shift_z, simulate_match, statistics,
                      validate_event_stream, validate_insight)
from app.main import app
from app.overlays import create_overlays
from app.pitch import pitch_state


def test_insights_publish_facts_and_hold_interpretations_for_review():
    events = generate_match()
    found = [i for m in range(20, 91) for i in detect_insights(events, m)]
    assert found
    for insight in found:
        assert insight['claim_type'] == 'observed_fact' and insight['type'] == 'advanced_activity_increase'
        meaning = insight['interpretation']
        assert meaning['status'] == 'review_required'
        assert meaning['z_score'] == shift_z(insight['current_count'], insight['previous_count'])
        assert meaning['meets_calibrated_threshold'] == (meaning['z_score'] >= SHIFT_Z_THRESHOLD)
        assert not validate_insight({**insight, 'interpretation': {**meaning, 'status': 'approved'}}, events)
        assert not validate_insight({**insight, 'interpretation': {**meaning, 'meets_calibrated_threshold': True,
                                                                   'z_score': 9.9}}, events)
    text = ' '.join(o.headline + ' ' + o.body for o in create_overlays(events, found)).lower()
    assert 'pressure' not in text and 'shift' not in text and 'review' not in text


def test_scenario_override_changes_only_the_label_strength():
    label = scenario_for(5001)
    strong = Scenario(label.kind, label.team, label.start_minute, 3.0) if label.team else label
    assert simulate_match(5001, scenario=strong)[1] == strong
    assert simulate_match(5001)[1] == label


def test_match_has_halves_set_pieces_and_squad_changes():
    events = generate_match()
    validate_event_stream(events)
    kinds = {e.set_piece for e in events if e.set_piece}
    assert {'kick_off', 'throw_in', 'goal_kick', 'corner', 'free_kick'} <= kinds
    kickoffs = [e for e in events if e.set_piece == 'kick_off']
    assert kickoffs[0].minute == 0 and any(e.minute == 45 and e.second < 5 for e in kickoffs)
    subs = [e for e in events if e.event_type == 'substitution']
    for team in ('home', 'away'):
        assert 3 <= sum(e.team_id == team for e in subs) <= 5
    assert all(e.minute >= 45 and e.possession_id == '' for e in subs)
    assert all(e.xg is not None and 0 < e.xg <= 1 for e in events if e.event_type == 'shot')


def test_unavailable_players_never_act_again():
    for seed in range(40):
        events = generate_match(seed)
        gone = {}
        for e in events:
            if e.event_type == 'substitution':
                gone[e.player_id] = e.sequence
            elif e.event_type == 'card' and e.outcome in SENDING_OFF:
                gone[e.player_id] = e.sequence
        for e in events:
            for player in (e.player_id, e.recipient_player_id):
                assert player not in gone or e.sequence <= gone[player]


def test_validator_rejects_lineup_and_booking_violations():
    sub = Event('s', 'm', 1, 60, 0, 'home', 'home-09', 'substitution', 50, 0, replacement_player_id='home-12')
    late = Event('p', 'm', 2, 61, 0, 'home', 'home-09', 'pass', 50, 50, 60, 50, recipient_player_id='home-10')
    with pytest.raises(ValueError, match='no longer'):
        validate_event_stream([sub, late])
    with pytest.raises(ValueError, match='substitution'):
        validate_event_stream([replace(late, sequence=0, minute=59, recipient_player_id='home-12'), sub])
    second = Event('c', 'm', 1, 30, 0, 'away', 'away-04', 'card', 40, 40, outcome='second_yellow')
    with pytest.raises(ValueError, match='booking'):
        validate_event_stream([second])
    yellow = replace(second, outcome='yellow')
    validate_event_stream([yellow, replace(second, event_id='c2', sequence=2, minute=31),
                           replace(second, event_id='c3', sequence=3, minute=32, outcome='red', player_id='away-05')])
    with pytest.raises(ValueError, match='xG'):
        validate_event_stream([replace(late, xg=.2)])
    with pytest.raises(ValueError, match='set piece'):
        validate_event_stream([replace(late, set_piece='penalty')])


def test_possession_time_is_causal_and_complete():
    events = generate_match()
    held = possession_seconds(events)
    assert all(v > 0 for v in held.values())
    stats = statistics(events)
    assert abs(stats['home']['possession_pct'] + stats['away']['possession_pct'] - 100) <= .2
    prefix = [e for e in events if e.minute < 30]
    assert possession_seconds(prefix) == possession_seconds([e for e in prefix])
    assert sum(possession_seconds(prefix).values()) <= 30 * 60


def test_scenario_labels_are_reproducible_and_hidden():
    assert scenario_for(20261020).team == 'away' and scenario_for(20261020).start_minute == 58
    assert simulate_match(7)[1] == scenario_for(7)
    kinds = {scenario_for(seed).kind for seed in range(60)}
    assert kinds == {'territorial_shift', 'control'}
    body = TestClient(app).get('/api/match').text
    assert 'territorial_shift' not in body and 'start_minute' not in body


def test_pitch_slots_follow_substitutions_and_sending_off():
    sub = Event('s', 'm', 1, 60, 0, 'home', 'home-09', 'substitution', 50, 0, replacement_player_id='home-14')
    red = Event('r', 'm', 2, 61, 0, 'away', 'away-04', 'card', 40, 40, outcome='red')
    pass_ = Event('p', 'm', 3, 62, 0, 'home', 'home-06', 'pass', 50, 50, 60, 50, recipient_player_id='home-14')
    players = {p['player_id']: p for p in pitch_state([sub, red, pass_], 63)['players']}
    assert len(players) == 22
    from app.squads import PLAYERS
    assert players['home-09']['occupant_id'] == 'home-14'
    assert players['home-09']['number'] == PLAYERS['home-14'].shirt and players['home-09']['name'] == PLAYERS['home-14'].name
    assert players['home-09']['active']
    assert players['away-04']['on_pitch'] is False and players['away-04']['occupant_id'] is None
    assert pitch_state([sub, red, pass_], 63)['ball']['source_event_id'] == 'p'
