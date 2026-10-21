import json
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.foundation import repository, DraftReview, digest

PASSWORD='Only for isolated test accounts 937!'

def post(client,path,body=None,**kwargs):
    session=client.get('/api/access/session').json()
    headers={'X-Pitchlight-Local':'1'}
    if session['csrf_token']:headers['X-CSRF-Token']=session['csrf_token']
    return client.post(path,json=body or {},headers=headers,**kwargs)

@pytest.fixture
def owner(tmp_path,monkeypatch):
    monkeypatch.setenv('MATCHMIND_FOUNDATION_DB',str(tmp_path/'access.sqlite3'))
    for flag in ['MATCHMIND_CORRECTIONS_ENABLED','MATCHMIND_REVIEW_ENABLED','MATCHMIND_PUBLICATION_ENABLED']:
        monkeypatch.setenv(flag,'true')
    client=TestClient(app)
    response=post(client,'/api/access/setup',{'username':'owner','password':PASSWORD})
    assert response.status_code==200
    return client

def view(client):return client.get('/api/foundation/state').json()

def review_body(v,decision='approve',key='authenticated-review-001'):
    return dict(seed=20261020,stream_id=v['context']['match_id'],draft_id=v['draft']['id'],
        expected_state_version=v['context']['state_version'],expected_body_hash=v['draft']['body_hash'],
        decision=decision,note='Reviewed source evidence and factual counts',idempotency_key=key)

def publish_body(v,key='publication-request-001'):
    return {k:val for k,val in review_body(v,key=key).items() if k not in {'decision','note'}}

def approve_publish(owner):
    v=view(owner)
    assert post(owner,'/api/foundation/reviews',review_body(v)).status_code==200
    response=post(owner,'/api/foundation/publications',publish_body(v));assert response.status_code==200
    return v,response.json()

def correct_body(v,e,key='correct-source-001'):
    return dict(seed=20261020,stream_id=v['context']['match_id'],event_id=e['event_id'],
        expected_state_version=v['context']['state_version'],outcome='failed',reason='Corrected reviewed source evidence',idempotency_key=key)

def test_sessions_password_hashes_and_logout(owner):
    session=owner.get('/api/access/session').json()
    assert session['user']['role']=='reviewer' and session['user']['is_owner']
    with repository().connect() as db:
        user=db.execute('SELECT * FROM access_users').fetchone()
        assert user['password_hash'].startswith('pbkdf2_sha256$600000$') and PASSWORD not in user['password_hash']
        assert db.execute('SELECT token_hash FROM access_sessions').fetchone()[0]!=owner.cookies['matchmind_session']
    assert post(owner,'/api/access/setup',{'username':'second','password':PASSWORD}).status_code==409
    assert post(owner,'/api/access/logout').status_code==200
    assert owner.get('/api/access/session').json()['user'] is None
    assert post(owner,'/api/foundation/reviews',review_body(view(owner))).status_code==401
    login=post(owner,'/api/access/login',{'username':'owner','password':PASSWORD})
    assert login.status_code==200
    cookie=login.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    with repository().connect() as db:db.execute('UPDATE access_sessions SET expires_at=?',(time.time()-1,))
    assert post(owner,'/api/foundation/reviews',review_body(view(owner))).status_code==401

def test_csrf_origin_and_role_enforcement(owner):
    v=view(owner)
    assert owner.post('/api/foundation/reviews',json=review_body(v)).status_code==403
    csrf=owner.get('/api/access/session').json()['csrf_token']
    r=owner.post('/api/foundation/reviews',json=review_body(v),headers={'X-Pitchlight-Local':'1','X-CSRF-Token':csrf,'Origin':'https://untrusted.example'})
    assert r.status_code==403
    assert post(owner,'/api/access/users',{'username':'analyst','password':PASSWORD,'role':'analyst'}).status_code==200
    analyst=TestClient(app)
    assert post(analyst,'/api/access/login',{'username':'analyst','password':PASSWORD}).status_code==200
    assert post(analyst,'/api/foundation/reviews',review_body(v)).status_code==403
    assert post(analyst,'/api/foundation/publications',publish_body(v)).status_code==403
    assert post(analyst,'/api/access/users',{'username':'elevated','password':PASSWORD,'role':'reviewer'}).status_code==403
    event=next(e for e in v['evidence_packet']['events'] if e['outcome']=='success')
    result=post(analyst,'/api/foundation/corrections',correct_body(v,event));assert result.status_code==200
    assert result.json()['actor']['username']=='analyst'
    forged={**review_body(view(owner)),'actor':{'role':'reviewer'}}
    assert post(analyst,'/api/foundation/reviews',forged).status_code==422

def test_login_throttle_and_validation_redaction(owner):
    for _ in range(5):assert post(owner,'/api/access/login',{'username':'owner','password':'Incorrect password 1!'}).status_code==401
    assert post(owner,'/api/access/login',{'username':'owner','password':PASSWORD}).status_code==429
    secret='too-short!'
    response=post(owner,'/api/access/login',{'username':'owner','password':secret})
    assert response.status_code==422 and secret not in response.text

def test_untrusted_host_and_missing_session_cannot_mutate(owner):
    assert owner.get('/api/access/session',headers={'Host':'untrusted.example'}).status_code==400
    anonymous=TestClient(app);v=view(owner)
    assert post(anonymous,'/api/foundation/corrections',correct_body(v,v['evidence_packet']['events'][0])).status_code==401
    assert post(anonymous,'/api/foundation/publications',publish_body(v)).status_code==401

def test_non_owner_reviewer_cannot_manage_accounts(owner):
    assert post(owner,'/api/access/users',{'username':'reviewer','password':PASSWORD,'role':'reviewer'}).status_code==200
    reviewer=TestClient(app)
    assert post(reviewer,'/api/access/login',{'username':'reviewer','password':PASSWORD}).status_code==200
    assert post(reviewer,'/api/access/users',{'username':'another','password':PASSWORD,'role':'analyst'}).status_code==403

def test_publication_checks_exact_state_body_and_evidence(owner):
    v=view(owner)
    assert post(owner,'/api/foundation/reviews',review_body(v)).status_code==200
    for field,value in [('expected_state_version',999),('expected_body_hash','0'*64),('stream_id','another-match')]:
        body={**publish_body(v),field:value}
        assert post(owner,'/api/foundation/publications',body).status_code==409
    with repository().connect() as db:
        db.execute('UPDATE event_versions SET hash=? WHERE event_id=?',('0'*64,v['evidence_packet']['events'][0]['event_id']))
    assert post(owner,'/api/foundation/publications',publish_body(v)).status_code==422

def test_publication_gate_receipt_feed_and_correction(owner):
    before=view(owner)
    assert post(owner,'/api/foundation/publications',publish_body(before)).status_code==409
    v,published=approve_publish(owner)
    assert post(owner,'/api/foundation/publications',publish_body(v)).json()==published
    feed=owner.get('/api/foundation/publications/feed').json()
    assert len(feed['items'])==1 and feed['external_delivery'] is False
    snapshot=feed['items'][0]['snapshot'];assert snapshot['approved_by']['username']=='owner'
    assert digest(snapshot)==published['snapshot_hash']
    event=next(e for e in v['evidence_packet']['events'] if e['outcome']=='success')
    assert post(owner,'/api/foundation/corrections',correct_body(v,event)).status_code==200
    assert owner.get('/api/foundation/publications/feed').json()['items']==[]
    after=view(owner)
    assert after['publications'][0]['status']=='withdrawn'
    assert post(owner,'/api/foundation/publications',publish_body(after,'unapproved-new-draft')).status_code==409
    with repository().connect() as db:
        row=db.execute('SELECT * FROM publications').fetchone()
        assert json.loads(row['snapshot'])==snapshot and row['snapshot_hash']==published['snapshot_hash']
    # A cached receipt cannot put a withdrawn item back into the live feed.
    assert post(owner,'/api/foundation/publications',publish_body(v)).json()==published
    assert owner.get('/api/foundation/publications/feed').json()['items']==[]
    assert TestClient(app).get('/api/foundation/publications/feed').status_code==401

def test_rejection_withdraws_and_unverified_approval_cannot_publish(owner):
    v=view(owner);repository().review(DraftReview(**review_body(v)))
    assert post(owner,'/api/foundation/publications',publish_body(v)).status_code==409
    # Authenticated attestation upgrades the legacy unverified approval.
    assert post(owner,'/api/foundation/reviews',review_body(v,key='authenticated-attestation')).status_code==200
    assert post(owner,'/api/foundation/publications',publish_body(v)).status_code==200
    assert post(owner,'/api/foundation/reviews',review_body(v,'reject','review-reject-001')).status_code==200
    assert not owner.get('/api/foundation/publications/feed').json()['items']
    assert view(owner)['publications'][0]['withdrawn_reason']=='Reviewer rejected this draft.'

@pytest.mark.parametrize('tamper',['snapshot','input_hash'])
def test_feed_withholds_inconsistent_content(owner,tamper):
    v,published=approve_publish(owner)
    with repository().connect() as db:
        if tamper=='snapshot':db.execute("UPDATE publications SET snapshot='{}'")
        else:db.execute('UPDATE event_versions SET hash=? WHERE event_id=?',('0'*64,v['evidence_packet']['events'][0]['event_id']))
    feed=owner.get('/api/foundation/publications/feed').json()
    assert feed['items']==[] and feed['withheld_count']==1

def test_unrelated_correction_keeps_published_evidence(owner):
    v,published=approve_publish(owner)
    event=next(e.json() for e in repository().snapshot(20261020)[2] if e.team_id=='home' and e.event_type=='pass' and e.outcome=='success')
    assert post(owner,'/api/foundation/corrections',correct_body(v,event)).status_code==200
    assert owner.get('/api/foundation/publications/feed').json()['items'][0]['id']==published['id']
