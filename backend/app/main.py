from __future__ import annotations
import asyncio
import os
import math
import time
import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

# Load backend/.env for local development; variables already set in the environment win.
# Tests set MATCHMIND_SKIP_DOTENV so a developer's secrets never reach the test suite.
if not os.getenv('MATCHMIND_SKIP_DOTENV'):
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    except ImportError:
        pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .core import GENERATOR_VERSION, statistics, detect_insights, validate_event_stream
from .narratives import AudienceRequest, publish_narratives
from .overlays import create_overlays, active_overlays
from .foundation import current_events as generate_match, router as foundation_router, repository as match_repository
from .pitch import pitch_state
from .runtime import validate_runtime, RuntimeBoundary, apply_demo_restrictions, is_demo
from .languages import LANGUAGE_PATTERN, catalogue
from .live import enrich

@asynccontextmanager
async def lifespan(app):
    apply_demo_restrictions(validate_runtime())
    from .telemetry import configure_tracing, shutdown_tracing
    configure_tracing()  # MATCHMIND_TRACING selects the exporter; off by default.
    match_repository()  # Initialize/check the data store before accepting traffic.
    from .graph import projection
    if projection.enabled():
        import threading
        threading.Thread(target=projection.project_at_startup, daemon=True, name='graph-projection').start()
    import threading as _threading

    def _warm_tactics():  # tracking-based shape is the slow part; compute the default match once
        try:
            from .tactics import change_points, impact
            source = match_repository().snapshot(20261020)[2]
            for point in change_points(source, 90):
                impact(source, point, 90, 'en')
        except Exception:
            pass
    _threading.Thread(target=_warm_tactics, daemon=True, name='tactics-warmup').start()
    # A session manager runs once, so each startup builds a fresh MCP app (tests start many).
    global _mcp_app
    from .mcp_server import server as mcp_server
    _mcp_app = _mcp_http_app()
    from . import feed
    consumer = asyncio.create_task(feed.consume()) if feed.enabled() else None  # Event Hubs match feed
    async with mcp_server.session_manager.run():  # serves /mcp
        yield
    if consumer is not None:
        consumer.cancel()
    shutdown_tracing()

app = FastAPI(title='MatchMind AI', version='0.1.0',lifespan=lifespan)
# MATCHMIND_ALLOWED_HOSTS adds a deployment's hostname (for example the Container App's FQDN).
_extra_hosts = [h.strip() for h in os.getenv('MATCHMIND_ALLOWED_HOSTS', '').split(',') if h.strip()]
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','[::1]','testserver', *_extra_hosts])
app.include_router(foundation_router)
from .access import router as access_router
app.include_router(access_router)
# MCP: the same verified match tools for any MCP client (agents, Copilot, Foundry), read-only.
from starlette.routing import Route as _Route
from .mcp_server import http_app as _mcp_http_app
_mcp_app = _mcp_http_app()


class _MCPEndpoint:
    """ASGI endpoint so /mcp is served exactly, without a trailing-slash redirect."""
    async def __call__(self, scope, receive, send):
        await _mcp_app(dict(scope, path='/', raw_path=b'/', root_path=scope.get('root_path', '') + '/mcp'),
                       receive, send)


app.router.routes.append(_Route('/mcp', endpoint=_MCPEndpoint(), methods=['GET', 'POST', 'DELETE']))
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo credentials back in validation diagnostics.
    return JSONResponse(status_code=422,content={'detail':[
        {'loc':list(e['loc']),'msg':e['msg'],'type':e['type']} for e in exc.errors()]})
from .research import router as research_router
app.include_router(research_router)
origins = os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://localhost:8080').split(',')
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET','POST'], allow_headers=['*'])
app.add_middleware(RuntimeBoundary)

@app.middleware('http')
async def request_context(request,call_next):
    request.state.request_id=uuid4().hex
    response=await call_next(request)
    response.headers['X-Request-ID']=request.state.request_id
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(sqlite3.Error)
async def database_unavailable(request,exc):
    request_id=getattr(request.state,'request_id',uuid4().hex)
    logging.getLogger('matchmind.database').warning('database_unavailable request_id=%s error_type=%s',request_id,type(exc).__name__)
    return JSONResponse(status_code=503,content={'detail':'Data store temporarily unavailable. Retry using the same request key.','request_id':request_id},headers={'Retry-After':'2','Cache-Control':'no-store'})

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.get('/ready')
def readiness():
    try:
        mode=validate_runtime()
        with match_repository().connect() as db:
            db.execute('SELECT state_version FROM streams LIMIT 1').fetchone()
    except (sqlite3.Error,OSError):
        return JSONResponse(status_code=503,content={'status':'not_ready','checks':{'foundation_store':'unavailable'},'production_ready':False},headers={'Cache-Control':'no-store'})
    return JSONResponse({'status':'ready','mode':mode,'checks':{'foundation_store':'available'},'production_ready':False},headers={'Cache-Control':'no-store'})

@app.get('/api/runtime')
def runtime_status():
    import importlib.util
    from .agents import selected_provider
    try:
        provider = selected_provider()
    except RuntimeError:
        provider = None
    configured = provider is not None
    sdk = importlib.util.find_spec('agent_framework_foundry') is not None
    # Report which settings are present, never their values.
    return {'provider': {'azure_openai': 'azure_openai', 'foundry': 'microsoft_foundry'}.get(provider, 'none'),
            'status': 'unverified' if configured and sdk else 'fallback',
            'configured': configured, 'sdk_installed': sdk,
            'auth': ('api_key' if os.getenv('AZURE_OPENAI_API_KEY') else 'entra_id') if provider == 'azure_openai'
                    else 'entra_id' if provider == 'foundry' else None,
            'live_inference_verified': False,
            'event_storage': 'sqlite' if os.getenv('MATCHMIND_EVENT_DB') else 'generated_in_memory'}

@app.get('/api/match')
def match(seed: int = Query(20261020, ge=0, le=2147483647)):
    events = generate_match(seed)
    return {'match_id': 'demo-001', 'seed': seed, 'total_events': len(events), 'statistics': statistics(events), 'generator_version': GENERATOR_VERSION}

@app.get('/api/state')
def state(minute: int = Query(67, ge=0, le=90), seed: int = Query(20261020, ge=0, le=2147483647)):
    stream, version, source = match_repository().snapshot(seed)
    visible = [e for e in source if e.minute < minute]
    return {'minute': minute, 'event_count': len(visible), 'events':[enrich(e) for e in visible[-4:]], 'statistics': statistics(visible), 'pitch': pitch_state(visible, minute),
            'context': {'match_id':stream,'seed':seed,'state_version':version,'minute':minute,'provider':'synthetic'},
            'insights': detect_insights(visible, minute)}

@app.get('/api/events')
def events(minute: int = Query(90, ge=0, le=90), seed: int = Query(20261020, ge=0, le=2147483647)):
    return [e.json() for e in generate_match(seed) if e.minute < minute]

@app.get('/api/insights')
def insights(minute: int = Query(67, ge=0, le=90), seed: int = Query(20261020, ge=0, le=2147483647)):
    evs = [e for e in generate_match(seed) if e.minute < minute]
    return detect_insights(evs, minute)

def _profile(audience: str, language: str, club: str | None, players: str | None,
             focus_player: str | None, metric: str | None):
    """Build and validate a viewer profile from query parameters; 422 on invalid values."""
    from fastapi import HTTPException
    from .experience import Profile
    try:
        return Profile(audience=audience, language=language, club=club or None,
                       players=tuple(p for p in (players or '').split(',') if p),
                       focus_player=focus_player or None, metric=metric or None).validate()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/overlays')
def overlays(minute: int = Query(67, ge=0, le=90), seed: int = Query(20261020, ge=0, le=2147483647),
             audience: str = Query('broadcast', pattern='^(fan|analyst|broadcast)$'),
             language: str = Query('en', pattern=LANGUAGE_PATTERN),
             active_only: bool = False, moments: bool = True,
             club: str | None = Query(None, pattern='^(home|away)$'), players: str | None = None,
             focus_player: str | None = None):
    from .experience import moments_for, personalized_moments
    from .overlays import moment_overlays
    profile = _profile(audience, language, club, players, focus_player, None)
    stream, version, source = match_repository().snapshot(seed)
    evs = [e for e in source if e.minute < minute]
    validate_event_stream(evs)
    # Insights at their original detection time retain a stable clock anchor.
    candidates = []
    for tick in range(20, minute + 1):
        candidates.extend(detect_insights([e for e in evs if e.minute < tick], tick))
    queue = create_overlays(evs, candidates, audience, language)
    if moments:
        feed = personalized_moments(moments_for(source, seed, minute, (stream, version)), profile, limit=200)
        queue += moment_overlays(feed, stream, audience, language)
    queue.sort(key=lambda o: (o.match_clock_seconds, -o.priority, o.overlay_id))
    if active_only:
        queue = active_overlays(queue, minute * 60)
    return {'context':{'match_id':stream,'state_version':version},'match_id': 'demo-001', 'minute': minute, 'overlays': [o.model_dump() for o in queue]}


@app.get('/api/recap/agent')
async def recap_agent_endpoint(minute: int = Query(90, ge=1, le=90), seed: int = Query(20261020, ge=0, le=2147483647),
                               language: str = Query('en', pattern=LANGUAGE_PATTERN),
                               audience: str = Query('fan', pattern='^(fan|analyst|broadcast)$'),
                               require_live: bool = False, http_request: Request = None):
    """Agent-written recap, fact-checked against verified results, scorers and claims."""
    from fastapi import HTTPException
    from .agents import FoundryAgentRuntime
    from .guard import GUARD, visitor
    stream, version, source = match_repository().snapshot(seed)
    key = ('recap', stream, version, minute, audience, language)
    if is_demo() and (hit := GUARD.cached(key)) is not None:
        return hit
    if is_demo() and not GUARD.allow(visitor(http_request)):
        raise HTTPException(429, 'Too many AI requests from this visitor. Try again in a minute.',
                            headers={'Retry-After': '60'})
    result = await FoundryAgentRuntime().run_recap(source, seed, minute, language, audience)
    if require_live and not result.trace.live:
        raise HTTPException(503, 'Live model execution unavailable; fallback is not accepted in this mode.')
    payload = {'context': {'match_id': stream, 'state_version': version}, **result.model_dump()}
    if is_demo():
        GUARD.store(key, payload)
    return payload


@app.get('/api/squads')
def squads_endpoint():
    from .squads import squads
    return squads()


@app.get('/api/players')
def players_endpoint(minute: int = Query(90, ge=0, le=90), seed: int = Query(20261020, ge=0, le=2147483647)):
    from .players import player_stats
    stream, version, source = match_repository().snapshot(seed)
    stats = player_stats(source, seed, minute)
    return {'context': {'match_id': stream, 'state_version': version, 'minute': minute},
            'players': sorted(stats.values(), key=lambda s: (s['team_id'], s['shirt'])),
            'physical_source': 'synthetic_physical'}


@app.get('/api/experience')
def experience_endpoint(minute: int = Query(67, ge=0, le=90), seed: int = Query(20261020, ge=0, le=2147483647),
                        audience: str = Query('fan', pattern='^(fan|analyst|broadcast)$'),
                        language: str = Query('en', pattern=LANGUAGE_PATTERN),
                        club: str | None = Query(None, pattern='^(home|away)$'), players: str | None = None,
                        focus_player: str | None = None, metric: str | None = None):
    """One viewer's personalized view of the verified match intelligence."""
    from .experience import experience
    profile = _profile(audience, language, club, players, focus_player, metric)
    stream, version, source = match_repository().snapshot(seed)
    return {'context': {'match_id': stream, 'state_version': version, 'minute': minute},
            **experience(source, seed, minute, profile, (stream, version))}


@app.get('/api/recap')
def recap_endpoint(minute: int = Query(90, ge=1, le=90), seed: int = Query(20261020, ge=0, le=2147483647),
                   language: str = Query('en', pattern=LANGUAGE_PATTERN),
                   club: str | None = Query(None, pattern='^(home|away)$'), players: str | None = None,
                   focus_player: str | None = None):
    """Half-time (minute=45), full-time (90) or match-so-far recap; every number is a validated claim."""
    from .recap import build_recap
    profile = _profile('fan', language, club, players, focus_player, None)
    stream, version, source = match_repository().snapshot(seed)
    return {'context': {'match_id': stream, 'state_version': version},
            **build_recap(source, seed, minute, profile, (stream, version))}

@app.websocket('/ws/match')
async def match_stream(ws: WebSocket):
    await ws.accept()
    try:
        seed = int(ws.query_params.get('seed', '20261020'))
        seed = min(max(seed, 0), 2147483647)
        speed = float(ws.query_params.get('speed', '0.2'))
        if not math.isfinite(speed):
            raise ValueError('Invalid speed')
        speed = min(max(speed, 0.05), 5)
        start_minute = int(ws.query_params.get('start_minute', '1'))
        if not 1 <= start_minute <= 90:
            raise ValueError('Invalid start minute')
        for minute in range(start_minute, 91):
            stream, version, events = match_repository().snapshot(seed)
            visible = [e for e in events if e.minute < minute]
            await ws.send_json({'minute': minute, 'statistics': statistics(visible),
                                'context':{'match_id':stream,'seed':seed,'state_version':version,'minute':minute,'provider':'synthetic'},
                                'pitch': pitch_state(visible, minute),
                                'events': [enrich(e) for e in visible[-4:]],
                                'insights': detect_insights(visible, minute),
                                'overlays': [o.model_dump() for o in create_overlays(visible, detect_insights(visible, minute))]})
            await asyncio.sleep(speed)
        await ws.close()
    except (ValueError, OverflowError):
        await ws.close(code=1008, reason='Invalid replay parameters')
    except (WebSocketDisconnect, RuntimeError):
        return

@app.websocket('/ws/live')
async def live_stream(ws: WebSocket):
    """Event-by-event live feed: every event is ingested, interpreted and personalized as it arrives.

    speed is match seconds per real second (60 plays the match in 90 real seconds).
    """
    from .core import Event
    from .experience import Profile
    from .live import LiveMatch
    await ws.accept()
    try:
        q = ws.query_params
        seed = min(max(int(q.get('seed', '20261020')), 0), 2147483647)
        speed = float(q.get('speed', '60'))
        if not math.isfinite(speed) or not 1 <= speed <= 3600:
            raise ValueError('Invalid speed')
        start_minute = int(q.get('start_minute', '0'))
        if not 0 <= start_minute < 90:
            raise ValueError('Invalid start minute')
        profile = Profile(audience=q.get('audience', 'fan'), language=q.get('language', 'en'),
                          club=q.get('club') or None, players=tuple(p for p in q.get('players', '').split(',') if p),
                          focus_player=q.get('focus_player') or None).validate()
        stream, version, source = match_repository().snapshot(seed)
        live = LiveMatch(seed, profile)
        await ws.send_json({'type': 'start', 'context': {'match_id': stream, 'state_version': version,
                                                          'seed': seed, 'speed': speed}})
        previous_clock = start_minute * 60
        for event in source:
            clock = event.minute * 60 + event.second
            messages = live.ingest(event)  # catch-up events before start_minute are ingested silently
            if event.minute < start_minute:
                continue
            await asyncio.sleep(min(max(clock - previous_clock, 0) / speed, 5))
            previous_clock = clock
            for message in messages:
                await ws.send_json(message)
        for message in live.finish():
            await ws.send_json(message)
        await ws.send_json({'type': 'end'})
        await ws.close()
    except (ValueError, OverflowError):
        await ws.close(code=1008, reason='Invalid live parameters')
    except (WebSocketDisconnect, RuntimeError):
        return


def _ingest_guard(request: Request):
    """External ingestion is off unless MATCHMIND_INGEST_TOKEN is set and presented."""
    from fastapi import HTTPException
    import hmac
    token = os.getenv('MATCHMIND_INGEST_TOKEN')
    if not token:
        raise HTTPException(403, 'Live ingestion disabled. Set MATCHMIND_INGEST_TOKEN to enable it.')
    if not hmac.compare_digest(request.headers.get('X-Ingest-Token', ''), token):
        raise HTTPException(401, 'Invalid ingest token.')


@app.post('/api/live/sessions')
def create_live_session(request: Request, seed: int = Query(20261020, ge=0, le=2147483647),
                        audience: str = Query('analyst', pattern='^(fan|analyst|broadcast)$'),
                        language: str = Query('en', pattern=LANGUAGE_PATTERN),
                        club: str | None = Query(None, pattern='^(home|away)$'), players: str | None = None,
                        focus_player: str | None = None):
    """Open a session that an external producer feeds one event at a time."""
    from .live import SESSIONS
    _ingest_guard(request)
    profile = _profile(audience, language, club, players, focus_player, None)
    return {'session_id': SESSIONS.create(seed, profile)}


@app.post('/api/live/sessions/{session_id}/events')
def ingest_live_events(session_id: str, events: list[dict], request: Request):
    """Ingest events in order. Each is validated against the stream so far; the first invalid
    event stops the batch and is reported, and nothing after it is applied."""
    from fastapi import HTTPException
    from .core import Event
    from .live import SESSIONS
    _ingest_guard(request)
    live = SESSIONS.get(session_id)
    if live is None:
        raise HTTPException(404, 'Unknown or expired live session.')
    messages, accepted = [], 0
    for raw in events:
        try:
            event = Event(**raw)
            messages += live.ingest(event)
        except (TypeError, ValueError) as exc:
            return JSONResponse(status_code=422, content={'accepted': accepted, 'rejected_index': accepted,
                                                          'reason': str(exc), 'messages': messages})
        accepted += 1
    return {'accepted': accepted, 'messages': messages}


@app.get('/api/narratives')
def narratives(request: AudienceRequest = Query()):
    events = [e for e in generate_match(request.seed) if e.minute < request.minute]
    validate_event_stream(events)
    insights = detect_insights(events, request.minute)
    return {
        'engine': 'deterministic_fallback',
        'microsoft_foundry_connected': False,
        'narratives': [n.model_dump() for n in publish_narratives(events, insights, request.audience, request.language)],
    }

@app.get('/api/languages')
def languages():
    return {'languages': catalogue()}

@app.get('/api/claims')
def claims(minute: int = Query(67, ge=1, le=90), seed: int = Query(20261020, ge=0, le=2147483647),
           metric: str | None = Query(None, pattern='^[a-z_]+$')):
    """Every supported, evidence-backed match claim before `minute`, from the corrected source."""
    from .claims import METRICS, match_claims, validate_claim
    if metric is not None and metric not in METRICS:
        from fastapi import HTTPException
        raise HTTPException(422, f'Unsupported metric. Supported: {", ".join(METRICS)}')
    stream, version, source = match_repository().snapshot(seed)
    found = [c for c in match_claims(source, minute) if metric is None or c['metric'] == metric]
    return {'context': {'match_id': stream, 'state_version': version, 'minute': minute},
            'claims': [c for c in found if validate_claim(c, source)[0]]}

@app.post('/api/claims/validate')
def claim_validation(claim: dict, seed: int = Query(20261020, ge=0, le=2147483647)):
    """Recompute a submitted claim against the current source; report why it fails."""
    from .claims import validate_claim
    stream, version, source = match_repository().snapshot(seed)
    valid, reason = validate_claim(claim, source)
    return {'valid': valid, 'reason': reason, 'context': {'match_id': stream, 'state_version': version}}

@app.get('/api/agents/run')
async def agent_run(minute: int = Query(67, ge=20, le=90), seed: int = Query(20261020, ge=0, le=2147483647),
                    audience: str = Query('fan', pattern='^(fan|analyst|broadcast)$'),
                    language: str = Query('en', pattern=LANGUAGE_PATTERN), require_live: bool = False,
                    http_request: Request = None):
    """Evidence-gated Microsoft agent execution; deterministic fallback without Azure credentials."""
    from .agents import FoundryAgentRuntime
    from .guard import GUARD, visitor
    stream, version, source = match_repository().snapshot(seed)
    key = ('narrative', stream, version, minute, audience, language)
    if is_demo() and (hit := GUARD.cached(key)) is not None:
        return hit
    if is_demo() and not GUARD.allow(visitor(http_request)):
        from fastapi import HTTPException
        raise HTTPException(429, 'Too many AI requests from this visitor. Try again in a minute.',
                            headers={'Retry-After': '60'})
    evs = [e for e in source if e.minute < minute]
    validate_event_stream(evs)
    result = await FoundryAgentRuntime().run(evs, detect_insights(evs, minute), audience, language)
    if require_live and not result.trace.live:
        from fastapi import HTTPException
        raise HTTPException(503, 'Live Foundry execution unavailable; fallback is not accepted in this mode.')
    if is_demo():
        GUARD.store(key, result.model_dump())
    return result.model_dump()


@app.get('/api/graph/network')
def graph_network(team: str = Query('away', pattern='^(home|away)$'),
                  minute: int = Query(67, ge=1, le=90),
                  window: int = Query(10, ge=1, le=45),
                  seed: int = Query(20261020, ge=0, le=2147483647)):
    from .graph.analytics import network_snapshot
    evs = generate_match(seed)
    return network_snapshot(evs, team, max(0, minute - window), minute)

@app.get('/api/graph/compare')
def graph_compare(team: str = Query('away', pattern='^(home|away)$'),
                  minute: int = Query(67, ge=20, le=90),
                  window: int = Query(10, ge=1, le=45),
                  seed: int = Query(20261020, ge=0, le=2147483647)):
    from fastapi import HTTPException
    from .graph.analytics import compare_windows
    try:
        stream, version, source = match_repository().snapshot(seed)
        return {**compare_windows(source, team, minute, window),'context':{'match_id':stream,'state_version':version}}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.get('/api/graph/health')
def graph_health():
    from .graph.config import repository_from_env
    try:
        repo = repository_from_env()
        try:
            return repo.health()
        finally:
            repo.close()
    except Exception as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={'status':'unavailable', 'reason':type(exc).__name__})

@app.post('/api/graph/rebuild')
def graph_rebuild(http_request:Request,seed: int = Query(20261020, ge=0, le=2147483647)):
    """Development-only projection replay; disabled unless explicitly enabled."""
    from fastapi import HTTPException
    if os.getenv('GRAPH_REBUILD_ENABLED', 'false').lower() != 'true':
        raise HTTPException(403, 'Graph rebuild disabled. Set GRAPH_REBUILD_ENABLED=true in a trusted environment.')
    from .access import require_user
    require_user(http_request,('reviewer',))
    from .graph.config import repository_from_env
    repo = repository_from_env()
    try:
        events = generate_match(seed)
        return {'match_id': 'demo-001', 'upserted_events': repo.upsert_events(events), 'backend': repo.backend}
    finally:
        repo.close()


_last_kickoff = float('-inf')  # monotonic time of the last start; -inf means never
_last_vision = float('-inf')
VISION_COOLDOWN = 20 * 60  # a video takes about 15 minutes to process on the job's CPU


@app.get('/api/feed')
def feed_status():
    """The Event Hubs match feed: consumer state, current run, counts and recent moments."""
    from .feed import FEED
    moments = [m for m in FEED.recent if m.get('type') == 'moment'][-12:]
    return {**FEED.status(), 'kickoff_available': bool(os.getenv('FEED_JOB_RESOURCE_ID')),
            'vision_available': bool(os.getenv('VISION_JOB_RESOURCE_ID')),
            'recent_moments': moments[::-1]}


@app.post('/api/feed/kickoff')
async def feed_kickoff(request: Request, source: str = Query('feed', pattern='^(feed|vision)$')):
    """Start a feed: the synthetic match publisher, or the vision job that recovers events from
    broadcast video. Both publish to Event Hubs; one of each runs at a time."""
    from fastapi import HTTPException
    from .feed import FEED, start_feed_job
    from .guard import GUARD, visitor
    global _last_kickoff, _last_vision
    job = os.getenv('VISION_JOB_RESOURCE_ID' if source == 'vision' else 'FEED_JOB_RESOURCE_ID')
    if not job:
        raise HTTPException(503, 'This feed is not configured in this environment.')
    if source == 'vision':
        if time.monotonic() - _last_vision < VISION_COOLDOWN:
            raise HTTPException(409, 'A video is already being processed. Its events will appear in the Event Hubs panel.')
    else:
        live = FEED.run is not None and FEED.run.get('status') == 'live'
        if live or time.monotonic() - _last_kickoff < 60:
            raise HTTPException(409, 'A match feed is already running. Watch it, or try again when it reaches full time.')
    if is_demo() and not GUARD.allow(visitor(request)):
        raise HTTPException(429, 'Too many requests from this visitor. Try again in a minute.', headers={'Retry-After': '60'})
    if source == 'vision':
        _last_vision = time.monotonic()
    else:
        _last_kickoff = time.monotonic()
    try:
        return {'status': 'starting', 'source': source, **await start_feed_job(job)}
    except Exception as exc:
        if source == 'vision':
            _last_vision = float('-inf')
        else:
            _last_kickoff = float('-inf')
        logging.getLogger('matchmind.feed').warning('feed_kickoff_failed error_type=%s', type(exc).__name__)
        raise HTTPException(502, 'Could not start the job.') from None


@app.websocket('/ws/feed')
async def feed_stream(ws: WebSocket):
    """Everything the Event Hubs consumer produces, as it happens; recent messages first."""
    from .feed import FEED
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    for message in list(FEED.recent):
        await ws.send_json(message)
    FEED.subscribers.add(queue)
    try:
        await ws.send_json({'type': 'status', **FEED.status()})
        while True:
            await ws.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        FEED.subscribers.discard(queue)


SEED = Query(20261020, ge=0, le=2147483647)


def _knowledge(seed: int, minute: int):
    from .knowledge import match_graph
    return match_graph(seed, minute)


@app.get('/api/graph/knowledge')
def graph_knowledge(minute: int = Query(90, ge=0, le=90), seed: int = SEED):
    """The match knowledge graph: what it holds, and whether the graph database copy is current."""
    from .graph import projection
    from .knowledge import NODE_KINDS, RELATIONS, summary
    g, _, context = _knowledge(seed, minute)
    status = projection.ensure(seed)
    return {'context': context, 'schema': {'nodes': NODE_KINDS, 'relationships': RELATIONS},
            'networkx': summary(g),
            'database': {k: v for k, v in status.items() if k != 'checked_at'}}


@app.get('/api/graph/why')
def graph_why(moment_id: str = Query(..., max_length=80), minute: int = Query(90, ge=1, le=90),
              seed: int = SEED):
    """Why a moment matters: facts, evidence, the build-up and the players' network roles."""
    from fastapi import HTTPException
    from .graph import projection
    from .knowledge import why
    g, _, context = _knowledge(seed, minute)
    try:
        result = why(g, moment_id)
    except KeyError:
        raise HTTPException(404, 'Unknown moment at this minute.') from None
    repo = projection.ready(seed)
    source = 'networkx'
    if repo is not None and minute == projection.FULL_MATCH:
        # The database answers the evidence path; it must agree with the in-process graph.
        result['evidence_event_ids'] = repo.kg_evidence(context['match_id'], moment_id)
        source = repo.backend
    return {**result, 'source': source, 'context': context}


@app.get('/api/graph/roles')
def graph_roles(team: str | None = Query(None, pattern='^(home|away)$'), start: int = Query(0, ge=0, le=89),
                end: int | None = Query(None, ge=1, le=90), minute: int = Query(90, ge=1, le=90), seed: int = SEED):
    """Both teams' pass networks with player names, hubs, connectors, betweenness and PageRank."""
    from .graph import projection
    from .knowledge import average_positions, network_roles, passing_graph
    end = min(end or minute, minute)
    g, _, context = _knowledge(seed, minute)
    repo = projection.ready(seed)
    teams = {}
    for t in ([team] if team else ['home', 'away']):
        teams[t] = network_roles(g, t, start, end)
        net = passing_graph(g, t, start, end)
        teams[t]['edges'] = [{'from': u, 'to': v, 'passes': d['weight']} for u, v, d in net.edges(data=True)]
        teams[t]['positions'] = average_positions(g, t, start, end)
        if repo is not None:
            # Pass lanes are also read with Cypher; the counts must agree with NetworkX.
            stored = repo.kg_pass_lanes(context['match_id'], t, start, end)
            teams[t]['database_agrees'] = sum(r['weight'] for r in stored) == teams[t]['completed_passes']
    return {'teams': teams, 'database': repo.backend if repo else None, 'context': context}


@app.get('/api/graph/xg-chain')
def graph_xg_chain(team: str | None = Query(None, pattern='^(home|away)$'), minute: int = Query(90, ge=1, le=90),
                   seed: int = SEED):
    from .knowledge import xg_chain
    g, _, context = _knowledge(seed, minute)
    return {'teams': {t: xg_chain(g, t) for t in ([team] if team else ['home', 'away'])}, 'context': context,
            'definition': 'xG chain: total xG of the possessions a player took part in. xG build-up: '
                          'the same without the shooter and the final pass.'}


@app.get('/api/graph/buildup')
def graph_buildup(team: str | None = Query(None, pattern='^(home|away)$'), minute: int = Query(90, ge=1, le=90),
                  limit: int = Query(5, ge=1, le=20), seed: int = SEED):
    from .knowledge import buildup_chains
    g, _, context = _knowledge(seed, minute)
    return {'teams': {t: buildup_chains(g, t, limit) for t in ([team] if team else ['home', 'away'])},
            'context': context}


@app.get('/api/graph/timeline')
def graph_timeline(team: str | None = Query(None, pattern='^(home|away)$'), minute: int = Query(90, ge=1, le=90),
                   language: str = Query('en', pattern=LANGUAGE_PATTERN), seed: int = SEED):
    """The developing story: moments in order along FOLLOWS, with the running score."""
    from .knowledge import timeline
    from .moments import render
    g, _, context = _knowledge(seed, minute)
    items = []
    for item in timeline(g, team):
        node_id = 'moment:' + item['moment_id']
        node = g.nodes[node_id]
        players = [v.removeprefix('player:') for _, v, k in g.out_edges(node_id, keys=True) if k == 'INVOLVES']
        moment = {'id': item['moment_id'], 'kind': item['kind'], 'team_id': item['team_id'], 'facts': node['facts'],
                  'why': node['why'], 'player_ids': players}
        items.append({**item, **render(moment, language)})
    return {'timeline': items, 'context': context}


@app.get('/api/graph/impact')
def graph_impact(event_id: str = Query(..., max_length=80), seed: int = SEED):
    """Every output that depends on an event: moments, claims, overlays and recaps."""
    from .graph import projection
    from .knowledge import impact
    g, _, context = _knowledge(seed, projection.FULL_MATCH)
    result, source = impact(g, event_id), 'networkx'
    repo = projection.ready(seed)
    if repo is not None:
        result.update(repo.kg_impact(context['match_id'], event_id))
        source = repo.backend
    return {**result, 'event_id': event_id, 'source': source, 'context': context}


@app.get('/api/tactics/changes')
def tactical_changes(minute: int = Query(90, ge=1, le=90), language: str = Query('en', pattern=LANGUAGE_PATTERN),
                     seed: int = SEED):
    """What changed after each substitution and red card: ten minutes before vs after for both teams,
    each swing ranked against the match's own ten-minute swings, with evidence and a causal caveat."""
    from .tactics import change_points, impact
    stream, version, source = match_repository().snapshot(seed)
    return {'context': {'match_id': stream, 'state_version': version, 'minute': minute},
            'changes': [impact(source, p, minute, language) for p in change_points(source, minute)]}


@app.get('/api/tactics/pressing')
def tactical_pressing(minute: int = Query(67, ge=5, le=90), window: int = Query(15, ge=5, le=45), seed: int = SEED):
    """Pressing (PPDA, high turnovers) and defensive shape (line height, width, compactness) for both teams."""
    from .tactics import pressing
    stream, version, source = match_repository().snapshot(seed)
    visible = [e for e in source if e.minute < minute]
    return {'context': {'match_id': stream, 'state_version': version, 'minute': minute}, **pressing(visible, minute, window)}


@app.get('/api/ask')
async def ask_match(request: Request, q: str = Query(..., min_length=2, max_length=300),
                    minute: int = Query(90, ge=0, le=90), language: str = Query('en', pattern=LANGUAGE_PATTERN),
                    seed: int = SEED):
    """Answer a question from verified facts. The model only routes the question; code answers."""
    from .agents import selected_provider
    from .ask import answer, keyword_intent, mcp_agent_answer
    from .guard import GUARD, visitor
    g, events, context = _knowledge(seed, max(minute, 1))
    result, router, intent = None, 'keywords', None
    use_model = os.getenv('MATCHMIND_ASK_MODEL', 'true').lower() == 'true' and selected_provider() is not None
    from .mcp_server import SEED as MCP_SEED
    if use_model and 1 <= minute and seed == MCP_SEED and (not is_demo() or GUARD.allow(visitor(request))):
        # The agent reaches the match tools over MCP, like any external MCP client would.
        from .agents import FoundryAgentRuntime
        runtime = FoundryAgentRuntime()
        try:
            url = os.getenv('MATCHMIND_MCP_URL', 'http://127.0.0.1:8000/mcp')
            result = await mcp_agent_answer(runtime._client(), q, minute, language, url)
            if result is not None:
                router = 'mcp_agent'
        except Exception as exc:
            logging.getLogger('matchmind.ask').warning('ask_agent_failed error_type=%s', type(exc).__name__)
        finally:
            await runtime._close()
    if result is None:
        intent = keyword_intent(q)
        result = answer(g, events, seed, minute, intent, language)
    return {**result, 'question': q, 'router': router, 'context': context}


_static = os.getenv('MATCHMIND_STATIC_DIR')
if _static and Path(_static).is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    @app.get('/app', include_in_schema=False)
    def spa_app():
        return FileResponse(Path(_static) / 'index.html')

    app.mount('/', StaticFiles(directory=_static, html=True), name='frontend')
