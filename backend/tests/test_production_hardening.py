from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app import main
from app.access import init as init_access
from app.backup import recovery_copy,verify
from app.foundation import MatchRepository,DraftReview,PublicationRequest,Correction,encoded,digest
from app.store import EventStore
from app.runtime import RuntimeConfigurationError

def published_repo(path):
    repo=MatchRepository(str(path));v=repo.view(20261020,67,'away')
    actor={'id':'test-reviewer','username':'test-reviewer','role':'reviewer','is_owner':True}
    common=dict(seed=20261020,stream_id=v['context']['match_id'],draft_id=v['draft']['id'],expected_state_version=1,expected_body_hash=v['draft']['body_hash'])
    repo.review(DraftReview(**common,decision='approve',note='Reviewed recovery test evidence',idempotency_key='review-recovery-001'),actor)
    publication=repo.publish(PublicationRequest(**common,idempotency_key='publish-recovery-001'),actor)
    return repo,v,publication

def test_connections_close_after_commit_and_rollback(tmp_path):
    repo=MatchRepository(str(tmp_path/'store.sqlite3'))
    with repo.connect() as db:db.execute('SELECT 1')
    with pytest.raises(sqlite3.ProgrammingError):db.execute('SELECT 1')
    with pytest.raises(ValueError):
        with repo.connect() as failed:
            failed.execute("INSERT INTO streams VALUES('rollback',1,'hash',1)")
            raise ValueError('force rollback')
    with pytest.raises(sqlite3.ProgrammingError):failed.execute('SELECT 1')
    with repo.connect() as db:assert db.execute("SELECT 1 FROM streams WHERE id='rollback'").fetchone() is None
    events=EventStore(str(tmp_path/'events.sqlite3'))
    with events._connect() as db:db.execute('SELECT 1')
    with pytest.raises(sqlite3.ProgrammingError):db.execute('SELECT 1')

def test_parallel_initialization_is_serialized(tmp_path):
    path=str(tmp_path/'concurrent.sqlite3')
    with ThreadPoolExecutor(max_workers=4) as pool:
        states=list(pool.map(lambda _:MatchRepository(path).snapshot(20261020)[1],range(8)))
    assert states==[1]*8

def test_verified_backup_restore_and_session_revocation(tmp_path):
    source=tmp_path/'source.sqlite3';repo,v,pub=published_repo(source)
    with repo.connect() as db:
        init_access(db)
        db.execute("INSERT INTO access_sessions VALUES('token-hash','test-reviewer','csrf',9999999999)")
    backup=tmp_path/'backups'/'backup.sqlite3';saved=recovery_copy(source,backup)
    assert saved['integrity']=='ok' and saved['counts']['access_sessions']==1
    event=next(e for e in v['evidence_packet']['events'] if e['outcome']=='success')
    repo.correct(Correction(seed=20261020,stream_id=v['context']['match_id'],event_id=event['event_id'],expected_state_version=1,outcome='failed',reason='Change after the backup snapshot',idempotency_key='post-backup-correction'))
    restored=tmp_path/'restored.sqlite3';result=recovery_copy(backup,restored,restore=True)
    assert result['sessions_revoked'] and result['counts']['access_sessions']==0
    recovery=MatchRepository(str(restored))
    assert recovery.snapshot(20261020)[1]==1 and repo.snapshot(20261020)[1]==2
    assert recovery.publication_feed(20261020)['items'][0]['snapshot']==pub['snapshot']
    assert repo.publication_feed(20261020)['items']==[]
    assert verify(backup)['sha256']==saved['sha256']
    with pytest.raises(FileExistsError):recovery_copy(source,backup)
    assert verify(backup)['sha256']==saved['sha256']
    with pytest.raises(ValueError):recovery_copy(source,source)

def test_backup_refuses_missing_or_unrelated_source(tmp_path):
    output=tmp_path/'new.sqlite3'
    with pytest.raises(ValueError):recovery_copy(tmp_path/'missing.sqlite3',output)
    unrelated=tmp_path/'other.sqlite3'
    with sqlite3.connect(unrelated) as db:db.execute('CREATE TABLE unrelated(id INTEGER)')
    with pytest.raises(ValueError):recovery_copy(unrelated,output)
    assert not output.exists()

@pytest.mark.parametrize('damage',['malformed_snapshot','missing_approval_actor','forged_body_with_valid_checksum'])
def test_feed_damage_is_withheld_without_500(tmp_path,damage):
    repo,v,pub=published_repo(tmp_path/'feed.sqlite3')
    with repo.connect() as db:
        if damage=='malformed_snapshot':db.execute("UPDATE publications SET snapshot='not-json'")
        elif damage=='missing_approval_actor':db.execute('UPDATE draft_reviews SET actor=NULL')
        else:
            snapshot={**pub['snapshot'],'body':'A fabricated tactical conclusion.'}
            db.execute('UPDATE publications SET snapshot=?,snapshot_hash=?',(encoded(snapshot),digest(snapshot)))
    result=repo.publication_feed(20261020)
    assert result['items']==[] and result['withheld_count']==1

def test_readiness_and_sanitized_store_failure(tmp_path,monkeypatch,caplog):
    monkeypatch.setenv('MATCHMIND_ENV','test')
    monkeypatch.setenv('MATCHMIND_FOUNDATION_DB',str(tmp_path/'ready.sqlite3'))
    client=TestClient(main.app)
    assert client.get('/health').status_code==200
    ready=client.get('/ready');assert ready.status_code==200 and ready.json()['production_ready'] is False
    def unavailable():raise sqlite3.OperationalError('secret-file-path-and-sensitive-content')
    monkeypatch.setattr(main,'match_repository',unavailable)
    assert client.get('/ready').status_code==503
    response=client.get('/api/state')
    assert response.status_code==503 and response.headers['Retry-After']=='2'
    assert response.json()['request_id']==response.headers['X-Request-ID']
    assert 'secret-file-path' not in response.text and 'secret-file-path' not in caplog.text
    assert response.headers['Cache-Control']=='no-store'

@pytest.mark.parametrize('mode',['production','prod','unknown',''])
def test_release_guard_denies_http_even_without_lifespan(monkeypatch,mode):
    monkeypatch.setenv('MATCHMIND_ENV',mode)
    response=TestClient(main.app).get('/health')
    assert response.status_code==503 and response.json()['production_ready'] is False

def test_production_startup_and_websocket_are_blocked(monkeypatch):
    monkeypatch.setenv('MATCHMIND_ENV','production')
    with pytest.raises(RuntimeConfigurationError):
        with TestClient(main.app):pass
    with pytest.raises(WebSocketDisconnect) as error:
        with TestClient(main.app).websocket_connect('/ws/match'):pass
    assert error.value.code==1008
