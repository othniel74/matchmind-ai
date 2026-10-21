"""Single-workspace local authentication. Use managed identity before cloud deployment."""
from __future__ import annotations
import hashlib
import hmac
import secrets
import time
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from .foundation import repository

router=APIRouter(prefix='/api/access')
COOKIE='matchmind_session'
TTL=8*60*60

class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username:str=Field(pattern=r'^[a-z0-9][a-z0-9_.-]{2,39}$')
    password:str=Field(min_length=12,max_length=128,repr=False)

class NewUser(Credentials):
    role:Literal['analyst','reviewer']='analyst'

def hash_password(password,salt=None):
    salt=salt or secrets.token_hex(16)
    value=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600_000).hex()
    return f'pbkdf2_sha256$600000${salt}${value}'

def password_matches(password,stored):
    _,iterations,salt,expected=stored.split('$')
    actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(iterations)).hex()
    return hmac.compare_digest(actual,expected)

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def init(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS access_users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,role TEXT NOT NULL,is_owner INTEGER NOT NULL,created_at REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS access_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,
        csrf_token TEXT NOT NULL,expires_at REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS access_attempts(key TEXT PRIMARY KEY,failures INTEGER NOT NULL,started_at REAL NOT NULL);
    ''')

def public_user(row):
    return {'id':row['id'],'username':row['username'],'role':row['role'],'is_owner':bool(row['is_owner'])}

def connection():
    db=repository().connect()
    try:init(db)
    except Exception:
        db.close()
        raise
    return db

def same_origin(request):
    # Custom header prevents simple cross-origin form requests, including login CSRF.
    if request.headers.get('X-Pitchlight-Local')!='1':raise HTTPException(403,'Missing local request header.')
    origin=request.headers.get('origin')
    permitted={str(request.base_url).rstrip('/'),'http://127.0.0.1:5173','http://localhost:5173',
               'http://127.0.0.1:5174','http://localhost:5174','http://localhost:8080','http://127.0.0.1:8080'}
    if origin and origin not in permitted:raise HTTPException(403,'Untrusted request origin.')

def require_user(request:Request,roles=('analyst','reviewer'),mutation=True):
    with connection() as db:
        row=db.execute('''SELECT u.*,s.csrf_token FROM access_sessions s JOIN access_users u ON u.id=s.user_id
          WHERE s.token_hash=? AND s.expires_at>?''',(token_hash(request.cookies.get(COOKIE,'')),time.time())).fetchone()
    if row is None:raise HTTPException(401,'Sign in to continue.')
    if row['role'] not in roles:raise HTTPException(403,'Reviewer access is required for this action.')
    if mutation:
        same_origin(request)
        supplied=request.headers.get('X-CSRF-Token','')
        if not supplied.isascii() or not hmac.compare_digest(supplied,row['csrf_token']):raise HTTPException(403,'Invalid session request token.')
    return public_user(row)

def start_session(db,user,request,response):
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    db.execute('DELETE FROM access_sessions WHERE expires_at<=?',(time.time(),))
    # Rotate an existing session on sign-in.
    db.execute('DELETE FROM access_sessions WHERE token_hash=?',(token_hash(request.cookies.get(COOKIE,'')),))
    db.execute('INSERT INTO access_sessions VALUES(?,?,?,?)',(token_hash(token),user['id'],csrf,time.time()+TTL))
    response.set_cookie(COOKIE,token,max_age=TTL,httponly=True,samesite='strict',secure=request.url.scheme=='https',path='/')
    response.headers['Cache-Control']='no-store'
    return {'user':public_user(user),'csrf_token':csrf,'needs_setup':False}

@router.get('/session')
def session(request:Request,response:Response):
    response.headers['Cache-Control']='no-store'
    with connection() as db:
        needs_setup=not db.execute('SELECT 1 FROM access_users LIMIT 1').fetchone()
        row=db.execute('''SELECT u.*,s.csrf_token FROM access_sessions s JOIN access_users u ON u.id=s.user_id
          WHERE s.token_hash=? AND s.expires_at>?''',(token_hash(request.cookies.get(COOKIE,'')),time.time())).fetchone()
    return {'user':public_user(row) if row else None,'csrf_token':row['csrf_token'] if row else None,'needs_setup':needs_setup}

@router.post('/setup')
def setup(body:Credentials,request:Request,response:Response):
    same_origin(request)
    if request.client is None or request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(403,'First-account setup is available on the local machine only.')
    password_hash=hash_password(body.password)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM access_users LIMIT 1').fetchone():raise HTTPException(409,'Workspace already initialized. Sign in instead.')
        uid=secrets.token_hex(16)
        db.execute('INSERT INTO access_users VALUES(?,?,?,?,?,?)',(uid,body.username,password_hash,'reviewer',1,time.time()))
        user=db.execute('SELECT * FROM access_users WHERE id=?',(uid,)).fetchone()
        return start_session(db,user,request,response)

@router.post('/login')
def login(body:Credentials,request:Request,response:Response):
    same_origin(request)
    key=token_hash(f'{request.client.host if request.client else "unknown"}:{body.username}')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        attempt=db.execute('SELECT * FROM access_attempts WHERE key=?',(key,)).fetchone()
        if attempt and time.time()-attempt['started_at']<900 and attempt['failures']>=5:
            raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')
        user=db.execute('SELECT * FROM access_users WHERE username=?',(body.username,)).fetchone()
        dummy='pbkdf2_sha256$600000$'+'00'*16+'$'+'00'*32
        valid=password_matches(body.password,user['password_hash'] if user else dummy)
        if not user or not valid:
            started=attempt['started_at'] if attempt and time.time()-attempt['started_at']<900 else time.time()
            failures=attempt['failures']+1 if attempt and time.time()-attempt['started_at']<900 else 1
            db.execute('INSERT OR REPLACE INTO access_attempts VALUES(?,?,?)',(key,failures,started))
            db.commit()  # Persist throttling before returning an authentication error.
            raise HTTPException(401,'Invalid username or password.')
        db.execute('DELETE FROM access_attempts WHERE key=?',(key,))
        return start_session(db,user,request,response)

@router.post('/logout')
def logout(request:Request,response:Response):
    require_user(request)
    with connection() as db:db.execute('DELETE FROM access_sessions WHERE token_hash=?',(token_hash(request.cookies.get(COOKIE,'')),))
    response.delete_cookie(COOKIE,path='/');response.headers['Cache-Control']='no-store'
    return {'signed_out':True}

@router.post('/users')
def create_user(body:NewUser,request:Request):
    owner=require_user(request,('reviewer',))
    if not owner['is_owner']:raise HTTPException(403,'Only the workspace owner can create local accounts.')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM access_users WHERE username=?',(body.username,)).fetchone():raise HTTPException(409,'Username already exists.')
        uid=secrets.token_hex(16)
        db.execute('INSERT INTO access_users VALUES(?,?,?,?,?,?)',(uid,body.username,hash_password(body.password),body.role,0,time.time()))
    return {'id':uid,'username':body.username,'role':body.role,'is_owner':False}
