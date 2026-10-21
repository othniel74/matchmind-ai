"""Cross-check against Sportmonks' match record. The fixture is hand-written in Sportmonks' v3 format
for the same fictional match as test_providers.py; no provider data is stored and no network is used."""
import copy

from app.providers.sportmonks import align, compare, reference, same_person
from app.providers.statsbomb import adapt
from tests.test_providers import EVENTS


def sm_event(kind, team_id, minute, extra=None, player=None, result=None):
    return {'type': {'developer_name': kind}, 'participant_id': team_id, 'minute': minute, 'extra_minute': extra,
            'player_name': player, 'result': result, 'sort_order': minute}


# Sportmonks lists Southvale (StatsBomb's away team) as home: the sides must be aligned by name.
FIXTURE = {
    'id': 9001, 'name': 'Southvale vs Northbank',
    'participants': [{'id': 20, 'name': 'Southvale', 'meta': {'location': 'home'}},
                     {'id': 10, 'name': 'Northbank', 'meta': {'location': 'away'}}],
    'events': [sm_event('YELLOWCARD', 20, 21, player='P. Fifteen'),
               sm_event('PENALTY', 10, 45, 2, 'Player 9', '0-1'),
               sm_event('SUBSTITUTION', 10, 61, player='Player Sub'),
               sm_event('YELLOWCARD', 10, 71, player='P. Eleven'),
               sm_event('YELLOWREDCARD', 20, 90, 3, 'P. Fifteen'),
               sm_event('PENALTY_SHOOTOUT_GOAL', 10, 120, player='Player 9')],
    'statistics': [{'participant_id': 10, 'location': 'away', 'type': {'developer_name': 'SHOTS_TOTAL'}, 'data': {'value': 1}},
                   {'participant_id': 20, 'location': 'home', 'type': {'developer_name': 'SHOTS_TOTAL'}, 'data': {'value': 2}},
                   {'participant_id': 10, 'location': 'away', 'type': {'developer_name': 'PASSES'}, 'data': {'value': 2}}],
}
NAMES = {'home': 'Northbank', 'away': 'Southvale'}


def run(fixture=FIXTURE):
    return compare(adapt(EVENTS, home_team_id=1, match_id='fixture'), align(reference(fixture), NAMES))


def test_reference_reads_the_record_and_skips_the_shootout():
    ref = reference(FIXTURE)
    assert ref['teams'] == {'home': 'Southvale', 'away': 'Northbank'}
    assert ref['score'] == {'home': 0, 'away': 1}
    assert ref['goals'] == [{'team': 'away', 'minute': 47, 'player': 'Player 9', 'own_goal': False, 'penalty': True}]
    assert ref['cards'] == {'home': {'yellow': 1, 'second_yellow': 1, 'red': 0},
                           'away': {'yellow': 1, 'second_yellow': 0, 'red': 0}}


def test_sides_are_aligned_by_team_name():
    ref = align(reference(FIXTURE), NAMES)
    assert ref['sides_swapped'] and ref['teams'] == NAMES and ref['score'] == {'home': 1, 'away': 0}
    assert align(ref, NAMES) is ref  # already aligned: unchanged


def test_matching_record_agrees_on_every_exact_check():
    report = run()
    assert report['agreed'] == report['checked'] == 8, [c for c in report['checks'] if not c['agrees']]
    goal = next(c for c in report['checks'] if c['check'].startswith('goal'))
    assert goal['matchmind'] == {'minute': 47, 'scorer': 'Player 9'}
    shots = {(d['team'], d['statistic']): d for d in report['statistics']}
    assert shots[('Northbank', 'shots')]['difference'] == 0 and shots[('Southvale', 'shots')]['difference'] == -1
    assert 'differently' in report['statistics_note']


def test_disagreements_are_reported_not_hidden():
    fixture = copy.deepcopy(FIXTURE)
    fixture['events'][1].update(minute=60, extra_minute=None)  # a different goal time
    fixture['events'].append(sm_event('GOAL', 20, 80, player='Someone Else', result='1-1'))
    report = run(fixture)
    failed = {c['check'] for c in report['checks'] if not c['agrees']}
    assert 'score' in failed
    assert any("60'" in c for c in failed) and any("80'" in c for c in failed)
    assert any(c.startswith('goal only in MatchMind') for c in failed)


def test_own_goal_side_comes_from_the_running_score():
    fixture = copy.deepcopy(FIXTURE)
    fixture['events'].append(sm_event('OWNGOAL', 20, 75, player='Defender', result='0-2'))
    assert reference(fixture)['score'] == {'home': 0, 'away': 2}


def test_player_names_match_across_providers():
    assert same_person('Lionel Messi', 'Lionel Andrés Messi Cuccittini')
    assert same_person('Ángel Di María', 'Ángel Fabián Di María Hernández')
    assert same_person('Kylian Mbappé', 'Kylian Mbappé Lottin')
    assert not same_person('Julián Álvarez', 'Lionel Andrés Messi Cuccittini')
    assert not same_person(None, 'Player 9')
