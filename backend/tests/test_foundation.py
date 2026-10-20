import pytest
from fastapi import HTTPException
from app.foundation import MatchRepository, Correction

def request(view,event,**kwargs):
    return Correction(seed=20261020,stream_id=view['context']['match_id'],event_id=event['event_id'],
        expected_state_version=view['context']['state_version'],outcome=kwargs.pop('outcome','failed'),
        reason='Reviewed original source pass',idempotency_key=kwargs.pop('key','test-correction-001'),**kwargs)

def test_correction_invalidates_and_persists(tmp_path):
    path=str(tmp_path/'foundation.sqlite3');repo=MatchRepository(path)
    before=repo.view(20261020,67,'away')
    event=next(e for e in before['evidence_packet']['events'] if e['outcome']=='success' and e['minute']>=57)
    command=request(before,event);result=repo.correct(command)
    assert {a['status'] for a in result['affected_artifacts']}=={'invalidated','needs_review'}
    assert len(result['affected_artifacts'])==3
    assert repo.correct(command)==result
    after=MatchRepository(path).view(20261020,67,'away')
    assert after['context']['state_version']==2
    assert after['observation']['current_passes']==before['observation']['current_passes']-1
    assert len(after['invalidated_artifacts'])==3
    updated=next(e for e in after['evidence_packet']['events'] if e['event_id']==event['event_id'])
    assert updated['version']==2 and updated['hash']!=event['hash']
    with repo.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM event_versions WHERE event_id=?',(event['event_id'],)).fetchone()[0]==2
    restored=repo.correct(request(after,event,outcome='success',recipient_player_id=event['recipient_player_id'],key='test-restore-001'))
    assert restored['new_version']==3
    assert repo.view(20261020,67,'away')['observation']['current_passes']==before['observation']['current_passes']

def test_conflicts_isolation_and_failed_input(tmp_path):
    repo=MatchRepository(str(tmp_path/'foundation.sqlite3'))
    before=repo.view(20261020,67,'away');other=repo.view(20261021,67,'away');home=repo.view(20261020,67,'home')
    event=next(e for e in before['evidence_packet']['events'] if e['outcome']=='failed')
    command=request(before,event,outcome='success',recipient_player_id='away-2')
    # Use an existing teammate id from the source to respect the event contract.
    command.recipient_player_id=next(e['recipient_player_id'] for e in before['evidence_packet']['events'] if e['recipient_player_id'] and e['recipient_player_id']!=event['player_id'])
    result=repo.correct(command)
    assert len(result['affected_artifacts'])==3
    assert repo.view(20261021,67,'away')==other
    assert repo.view(20261020,67,'home')['observation']['current_passes']==home['observation']['current_passes']
    with pytest.raises(HTTPException) as exc:repo.correct(request(before,event,key='stale-request-001'))
    assert exc.value.status_code==409
    changed=command.model_copy(update={'reason':'Different correction reason'})
    with pytest.raises(HTTPException) as exc:repo.correct(changed)
    assert exc.value.status_code==409
    assert all(e['minute']<67 for e in before['evidence_packet']['events'])

def test_invalid_correction_rolls_back(tmp_path):
    repo=MatchRepository(str(tmp_path/'foundation.sqlite3'));before=repo.view(20261020,67,'away')
    event=before['evidence_packet']['events'][0]
    with pytest.raises(HTTPException):repo.correct(request(before,event,outcome='success'))
    assert repo.snapshot(20261020)[1]==1
