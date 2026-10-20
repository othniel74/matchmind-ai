import copy
import pytest
from fastapi.testclient import TestClient
from app.claims import METRICS, make_claim, match_claims, validate_claim
from app.core import detect_insights, generate_match
from app.languages import LANGUAGES, SUPPORTED, format_number
from app.main import app
from app.narratives import publish_narratives
from app.overlays import create_overlays

EVENTS = generate_match()
VISIBLE = [e for e in EVENTS if e.minute < 67]
INSIGHTS = detect_insights(VISIBLE, 67)


def test_registry_is_complete_for_every_language():
    assert {'en', 'es', 'fr', 'pt', 'de', 'it', 'ar'} <= set(SUPPORTED)
    for spec in LANGUAGES.values():
        assert set(spec.metrics) == set(METRICS), spec.code
        assert set(spec.narrative) == {'headline', 'analyst', 'fan', 'broadcast'}
        assert set(spec.claims) == {'score', 'compare', 'team_value'}
        assert spec.direction in {'ltr', 'rtl'}
        assert all('{club}' in spec.narrative[k] for k in ('headline', 'fan'))


@pytest.mark.parametrize('code', SUPPORTED)
def test_narratives_and_overlays_keep_identical_facts_in_every_language(code):
    insight = INSIGHTS[0]
    for audience in ('fan', 'analyst', 'broadcast'):
        narrative = publish_narratives(VISIBLE, INSIGHTS, audience, code)[0]
        assert narrative.language == code and narrative.direction == LANGUAGES[code].direction
        assert str(insight['previous_count']) in narrative.body and str(insight['current_count']) in narrative.body
        assert '{' not in narrative.body + narrative.headline
    overlay = create_overlays(VISIBLE, INSIGHTS, 'broadcast', code)[0]
    english = create_overlays(VISIBLE, INSIGHTS, 'broadcast', 'en')[0]
    assert (overlay.previous_value, overlay.current_value, overlay.evidence_event_ids) == \
           (english.previous_value, english.current_value, english.evidence_event_ids)
    assert overlay.metric_label == LANGUAGES[code].metric_label


def test_number_and_score_formats_follow_each_language():
    assert format_number(53.3, '%', 'en') == '53.3%'
    assert format_number(53.3, '%', 'fr') == '53,3 %'
    assert format_number(53.3, '%', 'de') == '53,3 %'
    assert format_number(1.18, '', 'it') == '1,18'
    score = make_claim(EVENTS, 'score', 'goals', 90)['statements']
    assert ':' in score['de'] and '–' in score['en']
    assert all('{' not in s for c in match_claims(EVENTS, 67) for s in c['statements'].values())


def test_claim_statements_cover_every_language_and_reject_tampering():
    claim = make_claim(EVENTS, 'team_value', 'possession', 67, 'away')
    assert set(claim['statements']) == set(SUPPORTED)
    assert validate_claim(claim, EVENTS) == (True, 'valid')
    forged = copy.deepcopy(claim)
    forged['statements']['ar'] += ' بشكل حاسم'
    assert validate_claim(forged, EVENTS) == (False, 'statement_mismatch')


def test_language_api():
    client = TestClient(app)
    languages = client.get('/api/languages').json()['languages']
    assert [l['code'] for l in languages] == list(SUPPORTED)
    assert next(l for l in languages if l['code'] == 'ar')['direction'] == 'rtl'
    for code in SUPPORTED:
        assert client.get(f'/api/narratives?minute=67&language={code}').status_code == 200
    overlays = client.get('/api/overlays?minute=90&language=ar').json()['overlays']
    assert overlays and all(o['direction'] == 'rtl' for o in overlays)
    assert client.get('/api/narratives?minute=67&language=xx').status_code == 422
    assert client.get('/api/overlays?language=xx').status_code == 422
