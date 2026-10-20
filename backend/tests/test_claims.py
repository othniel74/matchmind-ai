import copy
import pytest
from fastapi.testclient import TestClient
from app.claims import METRICS, make_claim, match_claims, measure, validate_claim
from app.core import generate_match, statistics
from app.main import app

EVENTS = generate_match()


def test_every_generated_claim_validates_and_matches_statistics():
    for minute in (10, 45, 67, 90):
        claims = match_claims(EVENTS, minute)
        assert len(claims) == 1 + 3 * (len(METRICS) - 1)
        assert all(validate_claim(c, EVENTS) == (True, 'valid') for c in claims)
    stats = statistics([e for e in EVENTS if e.minute < 90])
    for team in ('home', 'away'):
        for metric, field in (('goals', 'goals'), ('shots', 'shots'), ('xg', 'xg'), ('corners', 'corners'),
                              ('pass_completion', 'pass_completion_pct'), ('possession', 'possession_pct'),
                              ('yellow_cards', 'yellow_cards'), ('substitutions', 'substitutions')):
            assert measure(EVENTS, metric, team, 90)[0] == stats[team][field]


def test_score_claim_wording():
    score = make_claim(EVENTS, 'score', 'goals', 90)
    assert score['statements']['en'] == f"Calderbrook {score['values']['home']}–{score['values']['away']} Merridge before minute 90."
    assert score['statements']['es'].startswith('Calderbrook ') and 'antes del minuto 90' in score['statements']['es']


@pytest.mark.parametrize('tamper,reason', [
    (lambda c: c['values'].update(home=c['values']['home'] + 1), 'value_mismatch'),
    (lambda c: c['evidence_event_ids'].pop(), 'evidence_mismatch'),
    (lambda c: c['statements'].update(en=c['statements']['en'] + ' A decisive spell.'), 'statement_mismatch'),
    (lambda c: c.update(metric='possession_won'), 'unsupported_claim'),
    (lambda c: c.update(team_id='home'), 'invalid_scope'),
    (lambda c: c.pop('minute'), 'malformed_claim'),
])
def test_tampered_claims_are_rejected(tamper, reason):
    claim = copy.deepcopy(make_claim(EVENTS, 'compare', 'shots', 67))
    tamper(claim)
    assert validate_claim(claim, EVENTS) == (False, reason)


def test_future_evidence_is_rejected():
    claim = copy.deepcopy(make_claim(EVENTS, 'team_value', 'fouls', 30, 'away'))
    later = next(e.event_id for e in EVENTS if e.minute >= 30)
    claim['evidence_event_ids'].append(later)
    assert validate_claim(claim, EVENTS) == (False, 'evidence_outside_scope')


def test_claims_reject_after_source_correction():
    from dataclasses import replace
    claim = make_claim(EVENTS, 'team_value', 'pass_completion', 67, 'home')
    target = next(e for e in EVENTS if e.event_type == 'pass' and e.team_id == 'home'
                  and e.outcome == 'success' and e.minute < 67)
    corrected = [replace(e, outcome='failed', recipient_player_id=None) if e is target else e for e in EVENTS]
    assert validate_claim(claim, corrected) == (False, 'value_mismatch')


def test_claim_api():
    client = TestClient(app)
    body = client.get('/api/claims?minute=67&metric=shots').json()
    assert {c['kind'] for c in body['claims']} == {'compare', 'team_value'}
    claim = body['claims'][0]
    assert client.post('/api/claims/validate?seed=20261020', json=claim).json()['valid']
    forged = {**claim, 'values': {k: v + 1 for k, v in claim['values'].items()}}
    assert client.post('/api/claims/validate', json=forged).json() == {
        **client.post('/api/claims/validate', json=forged).json(), 'valid': False, 'reason': 'value_mismatch'}
    assert client.get('/api/claims?metric=unknown').status_code == 422
