"""Provider adapter: StatsBomb's open-data format mapped into MatchMind's event contract.

The fixture is written by hand in StatsBomb's format with fictional teams and players; no
provider data is stored in this repository."""
from app.core import statistics
from app.providers.statsbomb import adapt, summarize

HOME, AWAY = {'id': 1, 'name': 'Northbank'}, {'id': 2, 'name': 'Southvale'}
P = {n: {'id': 100 + n, 'name': f'Player {n}'} for n in range(1, 30)}
index = iter(range(1, 1000))


def ev(kind, period, minute, second, team, player=None, location=(60, 40), **extra):
    e = {'id': f'e{next(index)}', 'index': len(EVENTS) + 1, 'period': period, 'minute': minute, 'second': second,
         'type': {'name': kind}, 'team': team, 'possession': 1 + len(EVENTS) // 4, 'location': list(location), **extra}
    if player:
        e['player'] = player
    EVENTS.append(e)
    return e


EVENTS: list[dict] = []
ev('Starting XI', 1, 0, 0, HOME, tactics={'lineup': [{'player': P[n], 'jersey_number': n} for n in range(1, 12)]})
ev('Starting XI', 1, 0, 0, AWAY, tactics={'lineup': [{'player': P[n], 'jersey_number': n - 11} for n in range(12, 23)]})
ev('Pass', 1, 0, 1, HOME, P[9], (60, 40), pass_={'type': {'name': 'Kick Off'}})
EVENTS[-1]['pass'] = {'end_location': [70, 30], 'recipient': P[8], 'type': {'name': 'Kick Off'}}
del EVENTS[-1]['pass_']
ev('Pass', 1, 3, 10, HOME, P[8], (80, 20))
EVENTS[-1]['pass'] = {'end_location': [110, 40], 'outcome': {'name': 'Incomplete'}}
ev('Ball Recovery', 1, 3, 14, AWAY, P[14], (15, 40))
ev('Duel', 1, 10, 2, HOME, P[6], (70, 50), duel={'type': {'name': 'Tackle'}, 'outcome': {'name': 'Won'}})
ev('Foul Committed', 1, 20, 0, AWAY, P[15], (40, 40), foul_committed={'card': {'name': 'Yellow Card'}})
ev('Carry', 1, 21, 0, HOME, P[7])
ev('Pressure', 1, 21, 5, AWAY, P[16])
ev('Shot', 1, 46, 30, HOME, P[9], (108, 40), under_pressure=True,
   shot={'outcome': {'name': 'Goal'}, 'statsbomb_xg': 0.78, 'type': {'name': 'Penalty'}})
ev('Pass', 2, 45, 5, AWAY, P[20], (60, 40))
EVENTS[-1]['pass'] = {'end_location': [75, 60], 'recipient': P[21], 'type': {'name': 'Kick Off'}}
ev('Substitution', 2, 60, 0, HOME, P[11], substitution={'replacement': {'id': 199, 'name': 'Player Sub'}})
ev('Bad Behaviour', 2, 70, 0, HOME, P[11], bad_behaviour={'card': {'name': 'Yellow Card'}})
ev('Foul Committed', 2, 92, 15, AWAY, P[15], (50, 30), foul_committed={'card': {'name': 'Second Yellow'}})
ev('Shot', 2, 93, 0, AWAY, P[20], (100, 30), shot={'outcome': {'name': 'Saved'}, 'statsbomb_xg': 0.12})
ev('Shot', 5, 121, 0, HOME, P[9], (108, 40), shot={'outcome': {'name': 'Goal'}, 'statsbomb_xg': 0.78})


def test_every_supported_type_maps_and_validates():
    result = adapt(EVENTS, home_team_id=1, match_id='fixture')
    report = result['report']
    assert report['rejected'] == []
    assert report['accepted_by_type'] == {'pass': 3, 'recovery': 1, 'tackle': 1, 'foul': 2, 'card': 3, 'shot': 2,
                                          'substitution': 1}
    assert report['not_represented'] == {'Starting XI': 2, 'Carry': 1, 'Pressure': 1, 'penalty shoot-out': 1}


def test_clock_periods_and_stoppage_time_are_kept():
    events = adapt(EVENTS, home_team_id=1)['events']
    goal = next(e for e in events if e.event_type == 'shot' and e.outcome == 'goal')
    assert (goal.period, goal.minute, goal.second) == (1, 46, 30)  # first-half stoppage time
    second_half = [e for e in events if e.period == 2]
    assert second_half[0].minute == 45  # the second half restarts at 45:00 after 46:30 of the first
    assert adapt(EVENTS, home_team_id=1)['report']['stoppage_time_events'] == 4


def test_players_coordinates_and_details():
    result = adapt(EVENTS, home_team_id=1)
    events, names = result['events'], result['roster']
    kick_off = events[0]
    assert kick_off.player_id == 'home-09' and kick_off.recipient_player_id == 'home-08'
    assert kick_off.set_piece == 'kick_off' and (kick_off.x, kick_off.y) == (50.0, 50.0)
    assert names['home-09']['name'] == 'Player 9' and names['away-04']['name'] == 'Player 15'
    penalty = next(e for e in events if e.event_type == 'shot' and e.outcome == 'goal')
    assert penalty.xg == 0.78 and penalty.set_piece == 'penalty' and penalty.under_pressure is True
    failed = events[1]
    assert failed.outcome == 'failed' and failed.recipient_player_id is None and failed.end_x == round(110 / 120 * 100, 1)
    sub = next(e for e in events if e.event_type == 'substitution')
    assert sub.replacement_player_id in names and names[sub.replacement_player_id]['name'] == 'Player Sub'


def test_cards_follow_real_rules():
    events = adapt(EVENTS, home_team_id=1)['events']
    cards = [(e.player_id, e.outcome) for e in events if e.event_type == 'card']
    # A yellow for a player already substituted (on the bench) is valid; a second yellow sends off.
    assert cards == [('away-04', 'yellow'), ('home-11', 'yellow'), ('away-04', 'second_yellow')]


def test_bench_booking_then_substitution_same_second_card_and_own_goal():
    # Found on the 2022 World Cup: substitutes booked on the bench before coming on, a Bad Behaviour
    # card in the same second as a pass, and own goals (counted in the report, not invented as shots).
    def e(i, kind, minute, second, team, player=None, **extra):
        d = {'id': f'x{i}', 'index': i, 'period': 1, 'minute': minute, 'second': second, 'type': {'name': kind},
             'team': team, 'possession': 1, 'location': [60, 40], **extra}
        return {**d, 'player': player} if player else d
    lineup = {'lineup': [{'player': P[n], 'jersey_number': n} for n in range(1, 12)]}
    away_lineup = {'lineup': [{'player': P[n], 'jersey_number': n - 11} for n in range(12, 23)]}
    events = [e(1, 'Starting XI', 0, 0, HOME, tactics=lineup), e(2, 'Starting XI', 0, 0, AWAY, tactics=away_lineup),
              e(3, 'Bad Behaviour', 10, 0, HOME, P[25], bad_behaviour={'card': {'name': 'Yellow Card'}}),
              e(4, 'Pass', 20, 5, HOME, P[8], **{'pass': {'end_location': [70, 40], 'recipient': P[9]}}),
              e(5, 'Bad Behaviour', 20, 5, AWAY, P[13], bad_behaviour={'card': {'name': 'Yellow Card'}}),
              e(6, 'Substitution', 30, 0, HOME, P[10], substitution={'replacement': P[25]}),
              e(7, 'Own Goal Against', 35, 0, AWAY, P[14]), e(8, 'Own Goal For', 35, 0, HOME)]
    result = adapt(events, home_team_id=1)
    report = result['report']
    assert report['rejected'] == []
    assert report['accepted_by_type'] == {'card': 2, 'pass': 1, 'substitution': 1}
    assert report['own_goals'] == {'home': 1, 'away': 0} and report['not_represented']['Own Goal Against'] == 1
    sub = next(x for x in result['events'] if x.event_type == 'substitution')
    assert result['roster'][sub.replacement_player_id]['name'] == 'Player 25'


def test_matchmind_analytics_run_on_adapted_data():
    result = adapt(EVENTS, home_team_id=1)
    summary = summarize(result)
    assert summary['statistics']['home']['goals'] == 1 and summary['statistics']['away']['goals'] == 0
    assert summary['statistics']['home']['xg'] == 0.78
    assert summary['pass_networks']['home']['completed_passes'] == 1
    assert statistics(result['events'])['away']['shots'] == 1
