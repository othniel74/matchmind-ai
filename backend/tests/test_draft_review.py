import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.foundation import MatchRepository, DraftReview, Correction, encoded, digest
from app.main import app

def command(view, **overrides):
    values=dict(seed=20261020,stream_id=view['context']['match_id'],draft_id=view['draft']['id'],
        expected_state_version=view['context']['state_version'],expected_body_hash=view['draft']['body_hash'],
        decision='approve',note='Checked the source passing evidence',idempotency_key='review-request-001')
    return DraftReview(**{**values,**overrides})

def test_review_persists_and_correction_revokes(tmp_path):
    path=str(tmp_path/'review.sqlite3');repo=MatchRepository(path);before=repo.view(20261020,67,'away')
    assert before['draft']['validation']['passed']
    request=command(before);approved=repo.review(request)
    assert approved['status']=='approved' and approved['published'] is False
    assert repo.review(request)==approved
    assert MatchRepository(path).view(20261020,67,'away')['draft']['status']=='approved'
    event=next(e for e in before['evidence_packet']['events'] if e['outcome']=='success')
    repo.correct(Correction(seed=20261020,stream_id=before['context']['match_id'],event_id=event['event_id'],
        expected_state_version=1,outcome='failed',reason='Corrected source after review',idempotency_key='correction-review-001'))
    after=repo.view(20261020,67,'away')
    assert after['draft']['status']=='draft'
    assert after['draft']['validation']['passed']
    assert [r['action'] for r in after['reviews']]==['approval_revoked','approved']
    with pytest.raises(HTTPException) as exc:
        repo.review(command(before,expected_state_version=2,idempotency_key='review-stale-draft'))
    assert exc.value.status_code==409

@pytest.mark.parametrize('tamper',['body','missing_edge','input_hash','observation','packet_status'])
def test_approval_rejects_invalid_evidence(tmp_path,tamper):
    repo=MatchRepository(str(tmp_path/'review.sqlite3'));view=repo.view(20261020,67,'away');stream=view['context']['match_id']
    with repo.connect() as db:
        if tamper=='body':
            row=db.execute('SELECT payload FROM graph_nodes WHERE stream=? AND id=?',(stream,view['draft']['id'])).fetchone()
            payload=json.loads(row[0]);payload['body']='The away press caused a guaranteed goal.'
            db.execute('UPDATE graph_nodes SET payload=? WHERE stream=? AND id=?',(encoded(payload),stream,view['draft']['id']))
        elif tamper=='missing_edge':
            db.execute("DELETE FROM graph_edges WHERE stream=? AND source=? AND relation='INPUT_TO'",(stream,view['evidence_packet']['events'][0]['node_id']))
        elif tamper=='input_hash':
            db.execute('UPDATE event_versions SET hash=? WHERE stream=? AND event_id=?',('0'*64,stream,view['evidence_packet']['events'][0]['event_id']))
        elif tamper=='observation':
            payload={**view['observation'],'current_passes':999}
            db.execute('UPDATE graph_nodes SET payload=? WHERE stream=? AND id=?',(encoded(payload),stream,view['observation']['id']))
        else:
            db.execute("UPDATE graph_nodes SET status='invalidated' WHERE stream=? AND id=?",(stream,view['evidence_packet']['id']))
    overrides={'expected_body_hash':digest('The away press caused a guaranteed goal.')} if tamper=='body' else {}
    with pytest.raises(HTTPException) as exc:repo.review(command(view,**overrides))
    assert exc.value.status_code==422
    with repo.connect() as db:assert db.execute('SELECT COUNT(*) FROM draft_reviews').fetchone()[0]==0

def test_reject_and_context_conflicts(tmp_path):
    repo=MatchRepository(str(tmp_path/'review.sqlite3'));view=repo.view(20261020,67,'away')
    assert repo.review(command(view,decision='reject'))['status']=='rejected'
    with pytest.raises(HTTPException) as exc:repo.review(command(view))
    assert exc.value.status_code==409  # same key, different decision
    assert repo.review(command(view,idempotency_key='approve-after-reject'))['status']=='approved'
    for overrides in [dict(expected_state_version=2),dict(expected_body_hash='0'*64),dict(stream_id='other-match'),dict(note='     ')]:
        with pytest.raises(HTTPException):repo.review(command(view,idempotency_key='invalid-request-001',**overrides))

def test_review_endpoint_disabled_by_default(monkeypatch):
    monkeypatch.delenv('MATCHMIND_REVIEW_ENABLED',raising=False)
    body=dict(seed=20261020,stream_id='synthetic',draft_id='draft',expected_state_version=1,
        expected_body_hash='0'*64,decision='approve',note='A local review',idempotency_key='disabled-request')
    assert TestClient(app).post('/api/foundation/reviews',json=body).status_code==403

def test_unrelated_source_change_keeps_approval(tmp_path):
    repo=MatchRepository(str(tmp_path/'review.sqlite3'));view=repo.view(20261020,67,'away')
    repo.review(command(view))
    event=next(e for e in repo.snapshot(20261020)[2] if e.team_id=='home' and e.event_type=='pass' and e.outcome=='success')
    result=repo.correct(Correction(stream_id=view['context']['match_id'],event_id=event.event_id,
        expected_state_version=1,outcome='failed',reason='Unrelated home pass correction',idempotency_key='unrelated-source-change'))
    assert not result['affected_artifacts']
    with repo.connect() as db:
        assert db.execute('SELECT status FROM graph_nodes WHERE stream=? AND id=?',(view['context']['match_id'],view['draft']['id'])).fetchone()[0]=='approved'
        assert repo.validate_draft(db,view['context']['match_id'],view['draft']['id'])['passed']

def test_empty_evidence_abstains(tmp_path):
    repo=MatchRepository(str(tmp_path/'review.sqlite3'));stream=repo.ensure(20261020)
    # Simulate a data adapter delivering no passes in the selected window.
    with repo.connect() as db:
        rows=repo.latest(db,stream)
        for r in rows:
            payload=json.loads(r['payload'])
            if payload['event_type']=='pass' and payload['team_id']=='away' and 47<=payload['minute']<67:
                db.execute('DELETE FROM event_versions WHERE stream=? AND event_id=?',(stream,r['event_id']))
    view=repo.view(20261020,67,'away')
    assert not view['draft']['validation']['passed']
    with pytest.raises(HTTPException) as exc:repo.review(command(view))
    assert exc.value.status_code==422
