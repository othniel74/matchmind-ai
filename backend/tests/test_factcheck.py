"""Try to fool the fact checker: a viewer's sentence, checked statement by statement by code."""
import asyncio

import pytest
from fastapi.testclient import TestClient

pytest.importorskip('agent_framework')

from app.agent_workflow import check_claims, verify_statements  # noqa: E402
from app.core import generate_match  # noqa: E402
from app.main import app  # noqa: E402
from app.recap import recap_facts  # noqa: E402
from tests.test_agents import scripted_client, statements  # noqa: E402

EVENTS = generate_match()
FACTS = recap_facts(EVENTS, 90)
SCORER = next(s for s in FACTS['scorers'] if s['goals'] == 2)   # Pedro Valença scored twice
WINNER = next(t for t, r in FACTS['result'].items() if r == 'won')


def run(text, extraction):
    client = scripted_client({'fact_checker': [extraction]})
    return asyncio.run(check_claims(client, text, EVENTS, 90))


def test_a_false_goal_count_is_caught():
    text = f"{SCORER['player']} scored a hat-trick"
    result = run(text, statements({'quote': text, 'type': 'scorer', 'team': SCORER['team_id'],
                                   'player': SCORER['player'], 'count': 3}))
    assert not result['publishable']
    assert result['statements'] == [{'quote': text, 'type': 'scorer', 'supported': False, 'reason': 'contradicts_scorers'}]


def test_true_statements_pass_and_a_cause_is_blocked():
    text = f"{SCORER['player']} scored twice, and the team won because of the pressing"
    result = run(text, statements(
        {'quote': f"{SCORER['player']} scored twice", 'type': 'scorer', 'team': SCORER['team_id'],
         'player': SCORER['player'], 'count': 2},
        {'quote': 'the team won because of the pressing', 'type': 'result', 'team': WINNER, 'relation': 'won',
         'gives_cause': True}))
    verdicts = {v['quote']: v for v in result['statements']}
    assert verdicts[f"{SCORER['player']} scored twice"]['supported']
    assert verdicts['the team won because of the pressing']['reason'] == 'unsupported_gives_cause'
    assert not result['publishable']


def test_numbers_are_never_published_from_free_text():
    club = {'home': 'Calderbrook', 'away': 'Merridge'}[WINNER]
    text = f'{club} won 5-0'
    result = run(text, statements({'quote': text, 'type': 'result', 'team': WINNER, 'relation': 'won'}))
    assert result['statements'][0] == {'quote': text, 'type': 'result', 'supported': False, 'reason': 'unsupported_number'}


def test_scorer_count_rule_in_the_workflow_checker_too():
    flags = dict.fromkeys(('mentions_match_time', 'gives_cause', 'mentions_chances_or_threat', 'is_prediction',
                           'judges_performance', 'claims_dominance'), False)
    base = {'type': 'scorer', 'team': SCORER['team_id'], 'player': SCORER['player'], 'relation': None,
            'metric': None, 'intensity': 'neutral', **flags}
    text = f"{SCORER['player']} scored"
    for count, ok in ((None, True), (2, True), (1, False), (3, False)):
        failure = verify_statements([{**base, 'quote': text, 'count': count}], text, None, EVENTS, 90)[0]
        assert (failure is None) == ok, count


def test_endpoint_without_a_model_says_so():
    body = TestClient(app).get('/api/factcheck', params={'text': 'Merridge won the match', 'minute': 90}).json()
    assert body['available'] is False and body['statements'] == [] and body['publishable'] is False
    assert TestClient(app).get('/api/factcheck', params={'text': 'x'}).status_code == 422
