from app.core import generate_match, detect_insights
from app.overlays import create_overlays, active_overlays
from fastapi.testclient import TestClient
from app.main import app


def fixture():
    events = generate_match(20261020)
    for minute in range(20,91):
        visible = [e for e in events if e.minute < minute]
        found = detect_insights(visible,minute)
        if found:
            return visible,found
    raise AssertionError('No synthetic insight generated')


def test_overlay_evidence_and_clock():
    events, insights = fixture()
    overlays = create_overlays(events, insights)
    assert overlays
    assert all(o.validation_status == 'approved' and o.evidence_event_ids for o in overlays)
    assert all(o.match_clock_seconds == i['minute']*60 for o,i in zip(overlays,insights))


def test_overlay_expiration():
    events, insights = fixture()
    overlay = create_overlays(events, insights)[0]
    assert active_overlays([overlay],overlay.match_clock_seconds)
    assert not active_overlays([overlay],overlay.match_clock_seconds+9)
    assert not active_overlays([overlay],overlay.match_clock_seconds-1)


def test_tampered_claim_not_published():
    events, insights = fixture()
    forged = {**insights[0], 'current_count': insights[0]['current_count']+1}
    assert create_overlays(events,[forged]) == []


def test_overlay_languages_and_audiences():
    events, insights = fixture()
    en = create_overlays(events,insights,'broadcast','en')[0]
    es = create_overlays(events,insights,'fan','es')[0]
    assert en.evidence_event_ids == es.evidence_event_ids
    assert en.body != es.body


def test_overlay_api():
    response = TestClient(app).get('/api/overlays?minute=90&language=es&audience=fan')
    assert response.status_code == 200
    assert all(o['validation_status']=='approved' for o in response.json()['overlays'])
