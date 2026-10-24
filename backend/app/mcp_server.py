"""Pitchlight as a Model Context Protocol (MCP) server.

Any MCP client (an Agent Framework agent, Foundry, VS Code / GitHub Copilot, Claude Desktop)
can query the same verified match intelligence the product shows: claims, moments and why
they matter, pass-network roles, xG chain, build-ups, the story so far, correction impact,
recaps and question answering. Every tool is read-only and time-scoped: nothing after
`minute` is used, and results carry the event IDs they rest on.

Served over streamable HTTP at /mcp by the API (see main.py), or over stdio:
    python -m app.mcp_server
"""
from __future__ import annotations
import os
from contextvars import ContextVar
from typing import Any, Literal
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

SEED = 20261020
# The match this request is about: set from /mcp?seed=N by the API, the featured match otherwise.
MATCH_SEED: ContextVar[int] = ContextVar('match_seed', default=SEED)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                            openWorldHint=False)
Team = Literal['home', 'away']
Language = Literal['en', 'es', 'fr', 'pt', 'de', 'it', 'ar']
Intent = Literal['score', 'scorers', 'stat', 'player', 'why_moment', 'key_player', 'buildup', 'momentum', 'change', 'pressing',
                 'unsupported']



def _allowed_hosts() -> list[str]:
    """Hosts the HTTP transport accepts (DNS-rebinding protection), as for the API."""
    extra = [h.strip() for h in os.getenv('MATCHMIND_ALLOWED_HOSTS', '').split(',') if h.strip()]
    return [h for host in ('localhost', '127.0.0.1', '[::1]', 'testserver', *extra) for h in (host, f'{host}:*')]


server = FastMCP(
    name='pitchlight',
    # Stateless JSON responses: any replica can answer any request, nothing is kept per client.
    streamable_http_path='/', stateless_http=True, json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=_allowed_hosts(), allowed_origins=[]),
    instructions=(
        'Verified intelligence for a synthetic football match: Calderbrook FC (home) v Merridge '
        'Athletic (away); the URL (/mcp?seed=N) selects the match. Use these tools instead of guessing. Every result is computed from the '
        'validated event stream up to `minute` (1-90) and cites evidence event IDs. Languages: '
        'en, es, fr, pt, de, it, ar. All clubs, players and data are fictional.'),
)


def _graph(minute: int):
    from .knowledge import match_graph
    return match_graph(MATCH_SEED.get(), max(1, min(90, minute)))


def _minute(minute: int) -> int:
    if not 1 <= minute <= 90:
        raise ToolError('minute must be between 1 and 90')
    return minute


@server.tool(annotations=READ_ONLY)
def match_state(minute: int = 90) -> dict[str, Any]:
    """Score, team statistics and the current control/chaos, tempo and momentum state."""
    from .core import statistics
    from .dynamics import state_at
    g, events, context = _graph(_minute(minute))
    visible = [e for e in events if e.minute < minute]
    goals = {t: sum(e.team_id == t and e.outcome == 'goal' for e in visible) for t in ('home', 'away')}
    return {'context': context, 'score': goals, 'statistics': statistics(visible),
            'dynamics': state_at(visible, minute)}


@server.tool(annotations=READ_ONLY)
def list_claims(minute: int = 90, metric: str | None = None) -> dict[str, Any]:
    """Evidence-backed statistical claims (shots, xG, possession, ...) valid at `minute`."""
    from .claims import match_claims, validate_claim
    _, events, context = _graph(_minute(minute))
    claims = [c for c in match_claims(events, minute) if metric is None or c['metric'] == metric]
    return {'context': context, 'claims': [c for c in claims if validate_claim(c, events)[0]]}


@server.tool(annotations=READ_ONLY)
def validate_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """Recompute a claim from the event stream and say whether it is still true, and why not."""
    from .claims import validate_claim as check
    _, events, context = _graph(90)
    valid, reason = check(claim, events)
    return {'valid': valid, 'reason': reason, 'context': context}


@server.tool(annotations=READ_ONLY)
def key_moments(minute: int = 90, language: Language = 'en', kinds: list[str] | None = None,
                limit: int = 15) -> dict[str, Any]:
    """Key moments so far (goals, big chances, cards, key-link changes, momentum ...), newest
    first, each with why it matters in the chosen language and its evidence."""
    from .moments import detect_moments, render
    from .squads import name
    _, events, context = _graph(_minute(minute))
    found = [m for m in detect_moments(events, MATCH_SEED.get(), minute) if kinds is None or m['kind'] in kinds]
    found.sort(key=lambda m: (-m['priority'], -m['clock_seconds']))
    return {'context': context, 'moments': [
        {'id': m['id'], 'kind': m['kind'], 'minute': m['clock_seconds'] // 60 + 1, 'team_id': m['team_id'],
         'players': [name(p) for p in m['player_ids']], **render(m, language),
         'evidence_event_ids': m['evidence_event_ids']} for m in found[:max(1, min(limit, 50))]]}


@server.tool(annotations=READ_ONLY)
def why_moment(moment_id: str, minute: int = 90) -> dict[str, Any]:
    """Why a moment matters: facts, evidence, the build-up that led to it, the involved
    players' pass-network roles in the 15 minutes before, and the previous moment."""
    from .knowledge import why
    g, _, context = _graph(_minute(minute))
    try:
        return {**why(g, moment_id), 'context': context}
    except KeyError:
        raise ToolError(f'Unknown moment at minute {minute}; list them with key_moments') from None


@server.tool(annotations=READ_ONLY)
def network_roles(team: Team, minute: int = 90, window_minutes: int | None = None) -> dict[str, Any]:
    """A team's pass network: hub (most involved), key link (highest betweenness), PageRank
    and the strongest passing lanes, over the whole match or the last `window_minutes`."""
    from .knowledge import network_roles as roles
    g, _, context = _graph(_minute(minute))
    start = max(0, minute - window_minutes) if window_minutes else 0
    return {**roles(g, team, start, minute), 'context': context}


@server.tool(annotations=READ_ONLY)
def xg_chain(team: Team, minute: int = 90) -> dict[str, Any]:
    """xG chain (xG of possessions a player took part in) and xG build-up (the same without
    the shooter and final pass), per player."""
    from .knowledge import xg_chain as chain
    g, _, context = _graph(_minute(minute))
    return {'players': chain(g, team), 'context': context}


@server.tool(annotations=READ_ONLY)
def goal_buildups(team: Team, minute: int = 90, limit: int = 5) -> dict[str, Any]:
    """Possessions that ended in a goal or shot, as the ordered chain of players and actions."""
    from .knowledge import buildup_chains
    g, _, context = _graph(_minute(minute))
    return {'buildups': buildup_chains(g, team, max(1, min(limit, 20))), 'context': context}


@server.tool(annotations=READ_ONLY)
def story_so_far(minute: int = 90, language: Language = 'en', important_only: bool = True) -> dict[str, Any]:
    """The developing story: moments in order with the running score."""
    from .knowledge import timeline
    from .moments import render
    g, _, context = _graph(_minute(minute))
    out = []
    for item in timeline(g):
        node = g.nodes['moment:' + item['moment_id']]
        if important_only and node['priority'] < 6:
            continue
        players = [v.removeprefix('player:') for _, v, k in g.out_edges('moment:' + item['moment_id'], keys=True)
                   if k == 'INVOLVES']
        moment = {'id': item['moment_id'], 'kind': item['kind'], 'team_id': item['team_id'],
                  'facts': node['facts'], 'why': node['why'], 'player_ids': players}
        out.append({**item, 'minute': item['clock'] // 60 + 1, **render(moment, language)})
    return {'timeline': out, 'context': context}


@server.tool(annotations=READ_ONLY)
def correction_impact(event_id: str) -> dict[str, Any]:
    """Every published output that depends on an event: moments, claims, overlays, recaps.
    Use before correcting an event to see what would need to be re-checked."""
    from .knowledge import impact
    g, _, context = _graph(90)
    return {**impact(g, event_id), 'event_id': event_id, 'context': context}


@server.tool(annotations=READ_ONLY)
def match_recap(minute: int = 90, language: Language = 'en') -> dict[str, Any]:
    """Deterministic recap (half-time, full-time or so far) where every number is a validated claim."""
    from .experience import Profile
    from .recap import build_recap
    _, events, context = _graph(_minute(minute))
    return {**build_recap(events, MATCH_SEED.get(), minute, Profile(language=language)), 'context': context}


@server.tool(annotations=READ_ONLY)
def answer_question(question: str, minute: int = 90, language: Language = 'en',
                    intent: Intent | None = None, team: Team | None = None, player: str | None = None,
                    metric: str | None = None) -> dict[str, Any]:
    """Answer a viewer's question about this match from verified facts (score, scorers, a
    statistic, a player, why a goal happened, the key player, build-up, momentum), worded from
    fixed templates with evidence. Pass the structured intent when known; otherwise it is read
    from the question. Questions outside the match data are refused."""
    from .ask import answer, keyword_intent, validate_intent
    g, events, context = _graph(_minute(minute))
    routed = (validate_intent({'intent': intent, 'team': team, 'player': player, 'metric': metric}, question[:300])
              if intent else keyword_intent(question[:300]))
    return {**answer(g, events, MATCH_SEED.get(), minute, routed, language), 'context': context}


@server.tool(annotations=READ_ONLY)
def tactical_changes(minute: int = 90, language: Language = 'en') -> dict[str, Any]:
    """What changed after each substitution and red card: ten minutes before vs after for both teams
    (final-third entries, shots, xG, pass completion, possession, PPDA, high turnovers, defensive line
    height, width, compactness, pass-network risers). Each swing is ranked against the match's own
    ten-minute swings. Coincidence only: never report these as causes."""
    from .tactics import change_points, impact
    _, events, context = _graph(_minute(minute))
    return {'changes': [impact(events, p, minute, language) for p in change_points(events, minute)], 'context': context}


@server.tool(annotations=READ_ONLY)
def pressing_and_shape(minute: int = 90, window_minutes: int = 15) -> dict[str, Any]:
    """Pressing (PPDA: lower is more intense; high turnovers) and defensive shape (line height, width,
    compactness in metres) for both teams over the last `window_minutes`."""
    from .tactics import pressing
    _, events, context = _graph(_minute(minute))
    visible = [e for e in events if e.minute < minute]
    return {**pressing(visible, minute, max(5, min(window_minutes, 45))), 'context': context}


@server.tool(annotations=READ_ONLY)
def squads() -> dict[str, Any]:
    """Both fictional squads: player IDs, names, shirt numbers and positions."""
    from .squads import CLUBS, PLAYERS
    return {'clubs': {t: vars(c) for t, c in CLUBS.items()},
            'players': [{'player_id': pid, **vars(p)} for pid, p in PLAYERS.items()]}


def http_app():
    """Stateless streamable-HTTP app for mounting under the API at /mcp. A session manager
    can run only once, so each call starts from a new one (FastMCP reuses an existing one)."""
    server._session_manager = None
    return server.streamable_http_app()


if __name__ == '__main__':
    server.run('stdio')
