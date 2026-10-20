"""Local match/evidence foundation. SQLite persists graph records; NetworkX traverses them.

This is a single-workspace development slice, not production authorization or Bolt parity.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Literal

import networkx as nx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from .core import Event, statistics, validate_event_stream
from .store import replay_events
from .graph.analytics import compare_windows
from .database import ClosingConnection

router = APIRouter(prefix='/api/foundation')

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return sha256(encoded(value).encode()).hexdigest()

class Correction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seed: int = Field(default=20261020, ge=0, le=2147483647)
    stream_id: str
    event_id: str
    expected_state_version: int = Field(ge=1)
    outcome: Literal['success', 'failed']
    recipient_player_id: str | None = None
    reason: str = Field(min_length=5, max_length=300)
    idempotency_key: str = Field(min_length=8, max_length=100)

class DraftReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seed: int = Field(default=20261020, ge=0, le=2147483647)
    stream_id: str
    draft_id: str
    expected_state_version: int = Field(ge=1)
    expected_body_hash: str = Field(pattern='^[a-f0-9]{64}$')
    decision: Literal['approve', 'reject']
    note: str = Field(min_length=5, max_length=300)
    idempotency_key: str = Field(min_length=8, max_length=100)

class PublicationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    seed:int=Field(default=20261020,ge=0,le=2147483647)
    stream_id:str
    draft_id:str
    expected_state_version:int=Field(ge=1)
    expected_body_hash:str=Field(pattern='^[a-f0-9]{64}$')
    idempotency_key:str=Field(min_length=8,max_length=100)

def passing_statement(team, minute, prior, current):
    return f'{team.title()} completed {current} passes in minutes {minute-10}–{minute}, compared with {prior} in minutes {minute-20}–{minute-10}. This measures passing activity, not a tactical cause.'

class MatchRepository:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS streams(id TEXT PRIMARY KEY, seed INTEGER, base_hash TEXT, state_version INTEGER);
              CREATE TABLE IF NOT EXISTS event_versions(stream TEXT, event_id TEXT, version INTEGER,
                state_version INTEGER, payload TEXT, hash TEXT, recorded_at TEXT,
                PRIMARY KEY(stream,event_id,version));
              CREATE TABLE IF NOT EXISTS graph_nodes(stream TEXT, id TEXT, kind TEXT, status TEXT, payload TEXT,
                PRIMARY KEY(stream,id));
              CREATE TABLE IF NOT EXISTS graph_edges(stream TEXT, source TEXT, target TEXT, relation TEXT,
                PRIMARY KEY(stream,source,target,relation));
              CREATE TABLE IF NOT EXISTS corrections(stream TEXT, key TEXT, request_hash TEXT, response TEXT,
                PRIMARY KEY(stream,key));
              CREATE TABLE IF NOT EXISTS draft_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,
                stream TEXT, draft_id TEXT, action TEXT, note TEXT, body_hash TEXT, state_version INTEGER,
                recorded_at TEXT);
              CREATE TABLE IF NOT EXISTS review_requests(stream TEXT, key TEXT, request_hash TEXT, response TEXT,
                PRIMARY KEY(stream,key));
              CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY,stream TEXT,draft_id TEXT,
                status TEXT,snapshot TEXT,snapshot_hash TEXT,created_at TEXT,withdrawn_reason TEXT);
              CREATE TABLE IF NOT EXISTS publication_requests(stream TEXT,key TEXT,request_hash TEXT,response TEXT,
                PRIMARY KEY(stream,key));
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns={r['name'] for r in db.execute('PRAGMA table_info(draft_reviews)')}
            if 'actor' not in columns:db.execute('ALTER TABLE draft_reviews ADD COLUMN actor TEXT')

    @staticmethod
    def withdraw(db,stream,story,reason):
        db.execute("UPDATE publications SET status='withdrawn',withdrawn_reason=? WHERE stream=? AND draft_id=? AND status='active'",(reason,stream,story))
        db.execute("UPDATE graph_nodes SET status='withdrawn' WHERE stream=? AND kind='Publication' AND id IN (SELECT id FROM publications WHERE stream=? AND draft_id=? AND status='withdrawn')",(stream,stream,story))

    def publish(self,request:PublicationRequest,actor):
        import uuid
        stream=self.ensure(request.seed)
        if stream!=request.stream_id:raise HTTPException(409,'Source context changed.')
        fingerprint=digest({'request':request.model_dump(),'actor':actor['id']})
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cached=db.execute('SELECT request_hash,response FROM publication_requests WHERE stream=? AND key=?',(stream,request.idempotency_key)).fetchone()
            if cached:
                if cached['request_hash']!=fingerprint:raise HTTPException(409,'Idempotency key reused with different content.')
                return json.loads(cached['response'])
            state=db.execute('SELECT state_version FROM streams WHERE id=?',(stream,)).fetchone()[0]
            if state!=request.expected_state_version:raise HTTPException(409,'State changed. Reload before publishing.')
            row=db.execute("SELECT * FROM graph_nodes WHERE stream=? AND id=? AND kind='StoryVersion'",(stream,request.draft_id)).fetchone()
            if row is None:raise HTTPException(404,'Draft not found.')
            body=json.loads(row['payload'])['body']
            if digest(body)!=request.expected_body_hash:raise HTTPException(409,'Draft content changed.')
            approval=db.execute('SELECT * FROM draft_reviews WHERE stream=? AND draft_id=? ORDER BY id DESC LIMIT 1',(stream,request.draft_id)).fetchone()
            if row['status']!='approved' or not approval or approval['action']!='approved' or not approval['actor'] or approval['body_hash']!=request.expected_body_hash:
                raise HTTPException(409,'An authenticated approval of this exact draft is required.')
            validation=self.validate_draft(db,stream,request.draft_id)
            if not validation['passed']:raise HTTPException(422,'Evidence validation failed. Publication withheld.')
            if db.execute("SELECT 1 FROM publications WHERE stream=? AND draft_id=? AND status='active'",(stream,request.draft_id)).fetchone():raise HTTPException(409,'Draft already published locally.')
            publication_id='publication:'+uuid.uuid4().hex;now=datetime.now(timezone.utc).isoformat()
            observation=db.execute("SELECT payload FROM graph_nodes WHERE stream=? AND id=?",(stream,f'observation:{request.draft_id.split(":",1)[1]}')).fetchone()
            snapshot={'publication_id':publication_id,'match_id':stream,'draft_id':request.draft_id,'body':body,
                'body_hash':request.expected_body_hash,'state_version':state,'approved_by':json.loads(approval['actor']),
                'published_by':actor,'published_at':now,'destination':'local_feed','observation':json.loads(observation['payload'])}
            packet=db.execute("SELECT source FROM graph_edges WHERE stream=? AND target=? AND relation='SUPPORTS'",(stream,request.draft_id)).fetchone()[0]
            obs=db.execute("SELECT source FROM graph_edges WHERE stream=? AND target=? AND relation='SUPPORTS'",(stream,packet)).fetchone()[0]
            snapshot['input_versions']=[r['source'] for r in db.execute("SELECT source FROM graph_edges WHERE stream=? AND target=? AND relation='INPUT_TO' ORDER BY source",(stream,obs))]
            snapshot_hash=digest(snapshot)
            db.execute('INSERT INTO publications VALUES(?,?,?,?,?,?,?,NULL)',(publication_id,stream,request.draft_id,'active',encoded(snapshot),snapshot_hash,now))
            self.node(db,stream,publication_id,'Publication','active',{'snapshot_hash':snapshot_hash})
            self.edge(db,stream,request.draft_id,publication_id,'PUBLISHES')
            result={'id':publication_id,'status':'active','snapshot':snapshot,'snapshot_hash':snapshot_hash}
            db.execute('INSERT INTO publication_requests VALUES(?,?,?,?)',(stream,request.idempotency_key,fingerprint,encoded(result)))
        return result

    def publication_feed(self,seed):
        stream=self.ensure(seed)
        with self.connect() as db:
            db.execute('BEGIN')
            active=[];withheld=0
            for row in db.execute("SELECT * FROM publications WHERE stream=? AND status='active' ORDER BY created_at DESC",(stream,)):
                try:
                    snapshot=json.loads(row['snapshot'])
                    draft=db.execute('SELECT status,payload FROM graph_nodes WHERE stream=? AND id=?',(stream,row['draft_id'])).fetchone()
                    approval=db.execute('SELECT action,actor,body_hash FROM draft_reviews WHERE stream=? AND draft_id=? ORDER BY id DESC LIMIT 1',(stream,row['draft_id'])).fetchone()
                    valid=(digest(snapshot)==row['snapshot_hash'] and draft is not None and draft['status']=='approved'
                        and approval is not None and approval['action']=='approved' and bool(approval['actor'])
                        and snapshot['match_id']==stream and snapshot['draft_id']==row['draft_id'] and snapshot['publication_id']==row['id']
                        and snapshot['body']==json.loads(draft['payload'])['body']
                        and snapshot['body_hash']==approval['body_hash']==digest(snapshot['body'])
                        and snapshot['approved_by']==json.loads(approval['actor'])
                        and self.validate_draft(db,stream,row['draft_id'])['passed'])
                except (ValueError,KeyError,TypeError):
                    valid=False
                if not valid:
                    withheld+=1;continue
                active.append({'id':row['id'],'status':'active','snapshot':snapshot,'snapshot_hash':row['snapshot_hash']})
        return {'match_id':stream,'destination':'local_feed','items':active,'withheld_count':withheld,'external_delivery':False}

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def node(db, stream, node_id, kind, status, payload):
        db.execute('INSERT INTO graph_nodes VALUES(?,?,?,?,?) ON CONFLICT(stream,id) DO NOTHING',
                   (stream, node_id, kind, status, encoded(payload)))

    @staticmethod
    def edge(db, stream, source, target, relation):
        db.execute('INSERT OR IGNORE INTO graph_edges VALUES(?,?,?,?)', (stream, source, target, relation))

    def ensure(self, seed):
        base = replay_events(seed)
        base_hash = digest([e.json() for e in base])
        stream = f'synthetic:{seed}:{base_hash[:16]}'
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM streams WHERE id=?', (stream,)).fetchone() is None:
                db.execute('INSERT INTO streams VALUES(?,?,?,1)', (stream, seed, base_hash))
                self.node(db, stream, stream, 'Match', 'current', {'seed': seed, 'base_hash': base_hash})
                for e in base:
                    payload = e.json()
                    db.execute('INSERT INTO event_versions VALUES(?,?,1,1,?,?,?)',
                               (stream, e.event_id, encoded(payload), digest(payload), datetime.now(timezone.utc).isoformat()))
                    eid = f'{e.event_id}@1'
                    self.node(db, stream, eid, 'EventVersion', 'current', {'event_id':e.event_id,'version':1,'hash':digest(payload)})
                    self.edge(db, stream, stream, eid, 'HAS_EVENT_VERSION')
        return stream

    @staticmethod
    def latest(db, stream):
        return db.execute('''SELECT v.* FROM event_versions v JOIN
          (SELECT event_id,MAX(version) version FROM event_versions WHERE stream=? GROUP BY event_id) m
          ON v.event_id=m.event_id AND v.version=m.version WHERE v.stream=?''', (stream, stream)).fetchall()

    def snapshot(self, seed):
        stream = self.ensure(seed)
        with self.connect() as db:
            db.execute('BEGIN')
            state = db.execute('SELECT state_version FROM streams WHERE id=?', (stream,)).fetchone()[0]
            rows = self.latest(db, stream)
        return stream, state, sorted([Event(**json.loads(r['payload'])) for r in rows], key=lambda e:e.sequence)

    def validate_draft(self, db, stream, story):
        """Validate the supported deterministic template, not arbitrary natural language."""
        checks = []
        def check(name, passed):
            checks.append({'name':name,'passed':bool(passed)})
        draft = db.execute('SELECT * FROM graph_nodes WHERE stream=? AND id=? AND kind=?',
                           (stream,story,'StoryVersion')).fetchone()
        if draft is None:
            return {'passed':False,'checks':[{'name':'draft_exists','passed':False}], 'scope':'deterministic passing template only'}
        parents = db.execute('''SELECT n.* FROM graph_edges e JOIN graph_nodes n
            ON n.stream=e.stream AND n.id=e.source
            WHERE e.stream=? AND e.target=? AND e.relation='SUPPORTS' AND n.kind='EvidencePacket' ''',(stream,story)).fetchall()
        packet = parents[0] if len(parents)==1 else None
        observations = [] if packet is None else db.execute('''SELECT n.* FROM graph_edges e JOIN graph_nodes n
            ON n.stream=e.stream AND n.id=e.source WHERE e.stream=? AND e.target=?
            AND e.relation='SUPPORTS' AND n.kind='Observation' ''',(stream,packet['id'])).fetchall()
        obs = observations[0] if len(observations)==1 else None
        check('valid_evidence_chain',packet is not None and obs is not None and packet['status']=='valid' and obs['status']=='valid')
        if obs is not None:
            payload=json.loads(obs['payload']);team=payload['team'];minute=payload['minute']
            latest=self.latest(db,stream)
            inputs=[r for r in latest if (lambda e:e['team_id']==team and minute-20<=e['minute']<minute and e['event_type']=='pass')(json.loads(r['payload']))]
            linked={r['source'] for r in db.execute("SELECT source FROM graph_edges WHERE stream=? AND target=? AND relation='INPUT_TO'",(stream,obs['id']))}
            expected={f'{r["event_id"]}@{r["version"]}' for r in inputs}
            check('complete_current_input_versions',linked==expected)
            check('input_hash_integrity',all(digest(json.loads(r['payload']))==r['hash'] and
                (lambda n:n is not None and json.loads(n['payload']).get('hash')==r['hash'])(db.execute('SELECT payload FROM graph_nodes WHERE stream=? AND id=?',(stream,f'{r["event_id"]}@{r["version"]}')).fetchone()) for r in inputs))
            check('nonempty_evidence',len(inputs)>0)
            comparison=compare_windows([Event(**json.loads(r['payload'])) for r in latest],team,minute)
            prior=comparison['previous']['metrics']['passes'];current=comparison['current']['metrics']['passes']
            check('recomputed_claim_values',payload['previous_passes']==prior and payload['current_passes']==current and payload['delta']==current-prior)
            check('supported_statement_only',json.loads(draft['payload'])['body']==passing_statement(team,minute,prior,current))
        return {'passed':all(c['passed'] for c in checks),'checks':checks,'scope':'deterministic passing template only; not a general hallucination detector'}

    def review(self, request: DraftReview, actor=None):
        stream=self.ensure(request.seed)
        if stream!=request.stream_id:raise HTTPException(409,'Source context changed.')
        fingerprint=digest({'request':request.model_dump(),'actor':actor['id'] if actor else None})
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cached=db.execute('SELECT request_hash,response FROM review_requests WHERE stream=? AND key=?',(stream,request.idempotency_key)).fetchone()
            if cached:
                if cached['request_hash']!=fingerprint:raise HTTPException(409,'Idempotency key reused with different content.')
                return json.loads(cached['response'])
            state=db.execute('SELECT state_version FROM streams WHERE id=?',(stream,)).fetchone()[0]
            if state!=request.expected_state_version:raise HTTPException(409,'State changed. Reload before reviewing.')
            row=db.execute("SELECT * FROM graph_nodes WHERE stream=? AND id=? AND kind='StoryVersion'",(stream,request.draft_id)).fetchone()
            if row is None:raise HTTPException(404,'Draft not found in this match.')
            body_hash=digest(json.loads(row['payload'])['body'])
            if body_hash!=request.expected_body_hash:raise HTTPException(409,'Draft content changed. Reload before reviewing.')
            if row['status'] not in {'draft','approved','rejected'}:raise HTTPException(409,'This draft has invalidated evidence. Review the recomputed draft instead.')
            if not request.note.strip() or len(request.note.strip())<5:raise HTTPException(422,'Provide a review note of at least five non-whitespace characters.')
            validation=self.validate_draft(db,stream,request.draft_id)
            if request.decision=='approve' and not validation['passed']:raise HTTPException(422,{'message':'Evidence validation failed. Approval withheld.','validation':validation})
            status='approved' if request.decision=='approve' else 'rejected'
            previous_review=db.execute('SELECT actor FROM draft_reviews WHERE stream=? AND draft_id=? ORDER BY id DESC LIMIT 1',(stream,request.draft_id)).fetchone()
            if row['status']==status and not (status=='approved' and actor and (not previous_review or not previous_review['actor'])):
                raise HTTPException(409,'Draft already has this review status.')
            db.execute('UPDATE graph_nodes SET status=? WHERE stream=? AND id=?',(status,stream,request.draft_id))
            if status=='rejected':self.withdraw(db,stream,request.draft_id,'Reviewer rejected this draft.')
            timestamp=datetime.now(timezone.utc).isoformat()
            cursor=db.execute('INSERT INTO draft_reviews(stream,draft_id,action,note,body_hash,state_version,recorded_at) VALUES(?,?,?,?,?,?,?)',
                (stream,request.draft_id,status,request.note.strip(),body_hash,state,timestamp))
            if actor:db.execute('UPDATE draft_reviews SET actor=? WHERE id=?',(encoded(actor),cursor.lastrowid))
            result={'review_id':cursor.lastrowid,'draft_id':request.draft_id,'status':status,'body_hash':body_hash,
                    'state_version':state,'validation':validation,'recorded_at':timestamp,'published':False,'reviewer':actor or 'local-demo-unverified'}
            db.execute('INSERT INTO review_requests VALUES(?,?,?,?)',(stream,request.idempotency_key,fingerprint,encoded(result)))
        return result

    def view(self, seed, minute, team):
        stream = self.ensure(seed)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('SELECT state_version FROM streams WHERE id=?', (stream,)).fetchone()[0]
            rows = self.latest(db, stream)
            events = sorted([Event(**json.loads(r['payload'])) for r in rows], key=lambda e:e.sequence)
            visible = [e for e in events if e.minute < minute]
            comparison = compare_windows(visible, team, minute)
            # Include every input pass, not only successful edges: a failed-to-success
            # correction must also invalidate the metric's previous result.
            inputs = [e for e in visible if e.team_id == team and minute-20 <= e.minute < minute and e.event_type=='pass']
            versions = {r['event_id']:r for r in rows}
            oid = f'observation:{version}:{team}:{minute}'
            packet = f'evidence:{version}:{team}:{minute}'
            story = f'draft:{version}:{team}:{minute}'
            prior = comparison['previous']['metrics']['passes']
            current = comparison['current']['metrics']['passes']
            text = passing_statement(team,minute,prior,current)
            obs = {'id':oid,'state_version':version,'team':team,'minute':minute,
                   'algorithm_version':'explicit-passing-window-v1','previous_passes':prior,'current_passes':current,
                   'delta':current-prior,'status':'valid'}
            self.node(db, stream, oid, 'Observation', 'valid', obs)
            self.node(db, stream, packet, 'EvidencePacket', 'valid', {'id':packet,'observation_id':oid})
            self.node(db, stream, story, 'StoryVersion', 'draft', {'id':story,'body':text,'engine':'deterministic','published':False})
            self.edge(db, stream, oid, packet, 'SUPPORTS')
            self.edge(db, stream, packet, story, 'SUPPORTS')
            evidence = []
            for e in inputs:
                r = versions[e.event_id]
                eid = f'{e.event_id}@{r["version"]}'
                self.edge(db, stream, eid, oid, 'INPUT_TO')
                evidence.append({'node_id':eid,'version':r['version'],'hash':r['hash'],**e.json()})
            last_change = db.execute('SELECT response FROM corrections WHERE stream=? ORDER BY rowid DESC LIMIT 1',(stream,)).fetchone()
            history = [dict(r) for r in db.execute("SELECT id,kind,status FROM graph_nodes WHERE stream=? AND status IN ('invalidated','needs_review') ORDER BY id", (stream,))]
            links = [dict(r) for r in db.execute('SELECT source,target,relation FROM graph_edges WHERE stream=? AND (target=? OR source=? OR source=?)', (stream,oid,oid,packet))]
            validation=self.validate_draft(db,stream,story)
            draft_status=db.execute('SELECT status FROM graph_nodes WHERE stream=? AND id=?',(stream,story)).fetchone()[0]
            reviews=[{**dict(r),'actor':json.loads(r['actor']) if r['actor'] else None} for r in db.execute('SELECT draft_id,action,note,body_hash,state_version,recorded_at,actor FROM draft_reviews WHERE stream=? ORDER BY id DESC LIMIT 50',(stream,))]
            authenticated_approval=next((bool(r['actor']) and r['action']=='approved' for r in reviews if r['draft_id']==story),False)
            publications=[dict(r) for r in db.execute('SELECT id,draft_id,status,snapshot_hash,created_at,withdrawn_reason FROM publications WHERE stream=? ORDER BY created_at DESC LIMIT 50',(stream,))]
        return {'context':{'workspace_id':'local-demo','match_id':stream,'source_match_id':'demo-001',
                'provider':'synthetic','seed':seed,'period':1 if minute<=45 else 2,'clock_seconds':minute*60,
                'minute':minute,'state_version':version,'quality_state':'synthetic_generated',
                'capabilities':{'events':True,'explicit_recipients':True,'real_tracking':False,'live_ai':False},
                'clock_basis':'synthetic elapsed minute; no stoppage time model'},
                'statistics':statistics(visible),'comparison':comparison,'observation':obs,
                'evidence_packet':{'id':packet,'events':evidence},'draft':{'id':story,'body':text,'body_hash':digest(text),'status':draft_status,'authenticated_approval':authenticated_approval,'engine':'deterministic','published':any(p['draft_id']==story and p['status']=='active' for p in publications),'validation':validation},
                'reviews':reviews,'review_enabled':os.getenv('MATCHMIND_REVIEW_ENABLED','false').lower()=='true',
                'publications':publications,'publication_enabled':os.getenv('MATCHMIND_PUBLICATION_ENABLED','false').lower()=='true',
                'relationships':links,'invalidated_artifacts':history,'last_correction':json.loads(last_change['response']) if last_change else None,
                'corrections_enabled':os.getenv('MATCHMIND_CORRECTIONS_ENABLED','false').lower()=='true',
                'storage':'SQLite versioned event and provenance graph; NetworkX analysis/traversal',
                'limitation':'Single local workspace. Authenticated mutation roles; public demo reads. No external delivery, cloud identity, live tracking or verified Bolt integration.'}

    def correct(self, request: Correction, actor=None):
        stream = self.ensure(request.seed)
        if stream != request.stream_id:
            raise HTTPException(409, 'Source match context does not match this seed and generator.')
        fingerprint = digest({'request':request.model_dump(),'actor':actor['id'] if actor else None})
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cached = db.execute('SELECT request_hash,response FROM corrections WHERE stream=? AND key=?', (stream, request.idempotency_key)).fetchone()
            if cached:
                if cached['request_hash'] != fingerprint:
                    raise HTTPException(409,'Idempotency key reused with different content.')
                return json.loads(cached['response'])
            state = db.execute('SELECT state_version FROM streams WHERE id=?', (stream,)).fetchone()[0]
            if state != request.expected_state_version:
                raise HTTPException(409,'State changed. Reload evidence before correcting.')
            row = db.execute('SELECT * FROM event_versions WHERE stream=? AND event_id=? ORDER BY version DESC LIMIT 1', (stream,request.event_id)).fetchone()
            if row is None:
                raise HTTPException(404,'Event not found in this match.')
            old = Event(**json.loads(row['payload']))
            if old.event_type != 'pass':
                raise HTTPException(422,'This local slice supports pass-outcome corrections only.')
            recipient = request.recipient_player_id if request.outcome=='success' else None
            if request.outcome=='success' and not recipient:
                raise HTTPException(422,'A completed pass requires an explicit recipient.')
            new = replace(old,outcome=request.outcome,recipient_player_id=recipient)
            events = [Event(**json.loads(r['payload'])) for r in self.latest(db,stream)]
            try:
                validate_event_stream(sorted([new if e.event_id==old.event_id else e for e in events],key=lambda e:e.sequence))
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from exc
            if new == old:
                raise HTTPException(422,'Correction does not change the event.')
            graph = nx.DiGraph()
            for edge in db.execute("SELECT source,target FROM graph_edges WHERE stream=? AND relation IN ('INPUT_TO','SUPPORTS')", (stream,)):
                graph.add_edge(edge['source'],edge['target'])
            old_node = f'{old.event_id}@{row["version"]}'
            affected = nx.descendants(graph,old_node) if old_node in graph else set()
            changed = []
            for nid in sorted(affected):
                node = db.execute('SELECT kind,status,payload FROM graph_nodes WHERE stream=? AND id=?',(stream,nid)).fetchone()
                if node and node['kind'] in {'Observation','EvidencePacket','StoryVersion'}:
                    if node['kind']=='StoryVersion' and node['status']=='approved':
                        db.execute('INSERT INTO draft_reviews(stream,draft_id,action,note,body_hash,state_version,recorded_at,actor) VALUES(?,?,?,?,?,?,?,?)',
                            (stream,nid,'approval_revoked',f'Source correction: {old.event_id}. {request.reason}',digest(json.loads(node['payload'])['body']),state+1,datetime.now(timezone.utc).isoformat(),encoded(actor) if actor else None))
                    if node['kind']=='StoryVersion':self.withdraw(db,stream,nid,f'Source correction: {old.event_id}. {request.reason}')
                    status = 'needs_review' if node['kind']=='StoryVersion' else 'invalidated'
                    db.execute('UPDATE graph_nodes SET status=? WHERE stream=? AND id=?',(status,stream,nid))
                    changed.append({'id':nid,'kind':node['kind'],'status':status})
            next_version = row['version']+1
            new_node = f'{old.event_id}@{next_version}'
            payload = new.json()
            db.execute('INSERT INTO event_versions VALUES(?,?,?,?,?,?,?)',(stream,old.event_id,next_version,state+1,encoded(payload),digest(payload),datetime.now(timezone.utc).isoformat()))
            db.execute('UPDATE streams SET state_version=? WHERE id=?',(state+1,stream))
            db.execute("UPDATE graph_nodes SET status='superseded' WHERE stream=? AND id=?",(stream,old_node))
            self.node(db,stream,new_node,'EventVersion','current',{'event_id':old.event_id,'version':next_version,'hash':digest(payload)})
            self.edge(db,stream,new_node,old_node,'SUPERSEDES')
            self.edge(db,stream,stream,new_node,'HAS_EVENT_VERSION')
            result={'match_id':stream,'state_version':state+1,'event_id':old.event_id,'old_version':row['version'],
                    'new_version':next_version,'affected_artifacts':changed,'reason':request.reason,
                    'old_event':old.json(),'new_event':new.json(),'idempotency_key':request.idempotency_key}
            result['actor']=actor
            result['knowledge_impact']=knowledge_impact(events,new,request.seed,stream,state)
            db.execute('INSERT INTO corrections VALUES(?,?,?,?)',(stream,request.idempotency_key,fingerprint,encoded(result)))
        return result

def knowledge_impact(events, new, seed, stream, state, minute=90):
    """What a correction changes across every output, from the match knowledge graph:
    moments and claims the old event supported, and which of them change, appear or disappear."""
    from .knowledge import build_graph, impact
    corrected = [new if e.event_id == new.event_id else e for e in events]
    before = build_graph(events, seed, minute, stream, state)
    after = build_graph(corrected, seed, minute, stream, state + 1)
    def outputs(g, kind, key):
        return {d[key]: {k: v for k, v in d.items() if k not in {'kind', key}}
                for _, d in g.nodes(data=True) if d['kind'] == kind}
    changes = {}
    for kind, key in (('Moment', 'moment_id'), ('Claim', 'claim_id')):
        old, new_ = outputs(before, kind, key), outputs(after, kind, key)
        changes[kind.lower() + 's'] = {'removed': sorted(old.keys() - new_.keys()), 'added': sorted(new_.keys() - old.keys()),
                                       'changed': sorted(k for k in old.keys() & new_.keys() if old[k] != new_[k])}
    depends = impact(before, new.event_id)
    touched = sorted({*changes['moments']['removed'], *changes['moments']['added'], *changes['moments']['changed']})
    return {'depends_on_event': depends, 'changes': changes,
            'overlays': [f'ovl-{m}' for m in touched],
            'recaps_need_refresh': bool(touched or any(changes['claims'].values()) or depends['recaps'])}

@lru_cache(maxsize=8)
def repository_at(path):
    return MatchRepository(path)

def repository():
    return repository_at(os.getenv('MATCHMIND_FOUNDATION_DB',str(Path(__file__).resolve().parents[1]/'data/foundation.sqlite3')))

def current_events(seed=20261020):
    return repository().snapshot(seed)[2]

@router.get('/state')
def foundation_state(seed:int=Query(20261020,ge=0,le=2147483647),minute:int=Query(67,ge=20,le=90),team:str=Query('away',pattern='^(home|away)$')):
    return repository().view(seed,minute,team)

@router.post('/corrections')
def foundation_correction(request:Correction,http_request:Request):
    if os.getenv('MATCHMIND_CORRECTIONS_ENABLED','false').lower()!='true':
        raise HTTPException(403,'Local correction sandbox disabled.')
    from .access import require_user
    return repository().correct(request,require_user(http_request))

@router.post('/reviews')
def draft_review(request:DraftReview,http_request:Request):
    if os.getenv('MATCHMIND_REVIEW_ENABLED','false').lower()!='true':
        raise HTTPException(403,'Local review sandbox disabled.')
    from .access import require_user
    return repository().review(request,require_user(http_request,('reviewer',)))

@router.post('/publications')
def publish_draft(request:PublicationRequest,http_request:Request):
    if os.getenv('MATCHMIND_PUBLICATION_ENABLED','false').lower()!='true':raise HTTPException(403,'Local publication disabled.')
    from .access import require_user
    return repository().publish(request,require_user(http_request,('reviewer',)))

@router.get('/publications/feed')
def publication_feed(http_request:Request,seed:int=Query(20261020,ge=0,le=2147483647)):
    from .access import require_user
    require_user(http_request,mutation=False)
    from fastapi.responses import JSONResponse
    return JSONResponse(repository().publication_feed(seed),headers={'Cache-Control':'no-store'})

@router.get('/events/{event_id}/versions')
def event_versions(event_id:str,seed:int=Query(20261020,ge=0,le=2147483647)):
    repo=repository();stream=repo.ensure(seed)
    with repo.connect() as db:
        rows=db.execute('SELECT version,state_version,payload,hash,recorded_at FROM event_versions WHERE stream=? AND event_id=? ORDER BY version',(stream,event_id)).fetchall()
    if not rows:raise HTTPException(404,'Event not found.')
    return {'match_id':stream,'event_id':event_id,'versions':[{**dict(r),'payload':json.loads(r['payload'])} for r in rows]}
