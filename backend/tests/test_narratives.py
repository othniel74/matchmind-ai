from fastapi.testclient import TestClient
from app.main import app
from app.core import generate_match, detect_insights
from app.narratives import publish_narratives


def test_personalization_preserves_evidence():
    events = [e for e in generate_match() if e.minute < 67]
    insights = detect_insights(events, 67)
    assert insights
    analyst = publish_narratives(events, insights, 'analyst', 'en')
    fan = publish_narratives(events, insights, 'fan', 'es')
    assert analyst and fan
    assert analyst[0].evidence_event_ids == fan[0].evidence_event_ids
    assert analyst[0].body != fan[0].body
    assert analyst[0].status == 'approved'


def test_tampered_claim_cannot_publish():
    events = [e for e in generate_match() if e.minute < 67]
    insights = detect_insights(events, 67)
    assert insights
    altered = dict(insights[0], current_count=999)
    assert publish_narratives(events, [altered], 'fan', 'en') == []


def test_narrative_api():
    client = TestClient(app)
    r = client.get('/api/narratives', params={'minute': 67, 'audience': 'broadcast', 'language': 'en'})
    assert r.status_code == 200, r.text
    assert r.json()['microsoft_foundry_connected'] is False
    assert r.json()['narratives']
    assert client.get('/api/narratives', params={'minute': 120}).status_code == 422
