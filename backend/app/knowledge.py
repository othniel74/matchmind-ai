"""Match knowledge graph: verified match intelligence as one typed graph, plus the queries
the product runs on it.

Nodes: Match, Team, Player, Possession, Event, Moment, Claim. Relationships:
HAS_TEAM, PLAYS_FOR, PERFORMED, RECEIVED_BY, IN_POSSESSION, BY_TEAM, NEXT, PASSED_TO,
EVIDENCES, INVOLVES, FOR_TEAM, SUPPORTS, FOLLOWS.

The graph is rebuilt from the verified event stream (the canonical log), so it never holds
facts the stream does not. Every query answer cites the event IDs it rests on. A database
projection of the same graph lives in graph/repository.py.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any
import networkx as nx
from .claims import METRICS, make_claim
from .core import ON_BALL_TYPES, TEAMS, Event, pass_difficulty
from .graph.analytics import roles
from .moments import detect_moments
from .squads import CLUBS, PLAYERS, name

NODE_KINDS = ('Match', 'Team', 'Player', 'Possession', 'Event', 'Moment', 'Claim')
RELATIONS = ('HAS_TEAM', 'PLAYS_FOR', 'PERFORMED', 'RECEIVED_BY', 'IN_POSSESSION', 'BY_TEAM', 'NEXT',
             'PASSED_TO', 'EVIDENCES', 'INVOLVES', 'FOR_TEAM', 'SUPPORTS', 'FOLLOWS')
CLAIM_METRICS = ('shots', 'shots_on_target', 'xg', 'possession', 'pass_completion', 'corners', 'fouls')


def _clock(e: Event) -> int:
    return e.minute * 60 + e.second


def possessions(events: list[Event]) -> dict[str, dict[str, Any]]:
    """Each possession's team, clock span, ordered events and how it ended."""
    out: dict[str, dict[str, Any]] = {}
    for e in events:
        if not e.possession_id:
            continue
        p = out.setdefault(e.possession_id, {'id': e.possession_id, 'team_id': e.team_id, 'start': _clock(e),
                                             'events': [], 'xg': 0.0, 'ended_with': 'turnover'})
        p['events'].append(e)
        p['end'] = _clock(e)
        if e.event_type == 'shot' and e.team_id == p['team_id']:
            p['xg'] = round(p['xg'] + (e.xg or 0), 3)
            p['ended_with'] = 'goal' if e.outcome == 'goal' else 'shot'
    for p in out.values():
        p['passes'] = sum(e.event_type == 'pass' and e.team_id == p['team_id'] for e in p['events'])
    return out


def build_graph(events: list[Event], seed: int, minute: int, match_id: str, state_version: int = 1) -> nx.MultiDiGraph:
    visible = [e for e in events if e.minute < minute]
    g = nx.MultiDiGraph(match_id=match_id, minute=minute, state_version=state_version)
    match = f'match:{match_id}'
    g.add_node(match, kind='Match', seed=seed, minute=minute, state_version=state_version)
    for team, club in CLUBS.items():
        g.add_node(f'team:{team}', kind='Team', team_id=team, name=club.name, short=club.short)
        g.add_edge(match, f'team:{team}', key='HAS_TEAM')
    for pid, p in PLAYERS.items():
        g.add_node(f'player:{pid}', kind='Player', player_id=pid, name=p.name, shirt=p.shirt,
                   position=p.position, team_id=p.team_id)
        g.add_edge(f'player:{pid}', f'team:{p.team_id}', key='PLAYS_FOR')
    for pid, p in possessions(visible).items():
        g.add_node(f'possession:{pid}', kind='Possession', possession_id=pid, team_id=p['team_id'], start=p['start'],
                   end=p['end'], passes=p['passes'], xg=p['xg'], ended_with=p['ended_with'])
        g.add_edge(f'possession:{pid}', f'team:{p["team_id"]}', key='BY_TEAM')
        previous = None
        for e in p['events']:
            if previous is not None:
                g.add_edge(f'event:{previous.event_id}', f'event:{e.event_id}', key='NEXT')
            previous = e
    passes: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in visible:
        node = f'event:{e.event_id}'
        g.add_node(node, kind='Event', event_id=e.event_id, event_type=e.event_type, outcome=e.outcome,
                   team_id=e.team_id, clock=_clock(e), minute=e.minute, xg=e.xg, speed_kmh=e.speed_kmh,
                   set_piece=e.set_piece, x=e.x, y=e.y, end_x=e.end_x, end_y=e.end_y,
                   pass_difficulty=pass_difficulty(e) if e.event_type == 'pass' else None)
        g.add_edge(f'player:{e.player_id}', node, key='PERFORMED')
        if e.possession_id:
            g.add_edge(node, f'possession:{e.possession_id}', key='IN_POSSESSION')
        if e.event_type == 'pass' and e.outcome == 'success' and e.recipient_player_id:
            g.add_edge(node, f'player:{e.recipient_player_id}', key='RECEIVED_BY')
            passes[(e.player_id, e.recipient_player_id)].append(e.event_id)
    for (a, b), ids in passes.items():
        g.add_edge(f'player:{a}', f'player:{b}', key='PASSED_TO', weight=len(ids), event_ids=ids)
    previous = None
    for m in detect_moments(events, seed, minute):
        node = f'moment:{m["id"]}'
        g.add_node(node, kind='Moment', moment_id=m['id'], moment_kind=m['kind'], clock=m['clock_seconds'],
                   why=m['why'], priority=m['priority'], team_id=m['team_id'], facts=m['facts'])
        for event_id in m['evidence_event_ids']:
            if f'event:{event_id}' in g:
                g.add_edge(f'event:{event_id}', node, key='EVIDENCES')
        for pid in m['player_ids']:
            g.add_edge(node, f'player:{pid}', key='INVOLVES')
        if m['team_id']:
            g.add_edge(node, f'team:{m["team_id"]}', key='FOR_TEAM')
        if previous is not None:
            g.add_edge(previous, node, key='FOLLOWS')
        previous = node
    if minute >= 1:
        for metric in CLAIM_METRICS:
            claim = make_claim(events, 'compare', metric, minute)
            node = f'claim:{claim["claim_id"]}'
            g.add_node(node, kind='Claim', claim_id=claim['claim_id'], metric=metric, values=claim['values'])
            for event_id in claim['evidence_event_ids']:
                if f'event:{event_id}' in g:
                    g.add_edge(f'event:{event_id}', node, key='SUPPORTS')
    return g


def passing_graph(g: nx.MultiDiGraph, team: str, start: int = 0, end: int = 90) -> nx.DiGraph:
    """Weighted pass network for one team within [start, end) minutes, from the knowledge graph."""
    net = nx.DiGraph()
    for pid, p in PLAYERS.items():
        if p.team_id == team:
            net.add_node(pid)
    for u, v, key, data in g.edges(keys=True, data=True):
        if key != 'RECEIVED_BY':
            continue
        event = g.nodes[u]
        if event['team_id'] != team or not start <= event['minute'] < end:
            continue
        passer = next(p for p, _, k in g.in_edges(u, keys=True) if k == 'PERFORMED')
        a, b = passer.removeprefix('player:'), v.removeprefix('player:')
        if net.has_edge(a, b):
            net[a][b]['weight'] += 1
            net[a][b]['event_ids'].append(event['event_id'])
        else:
            net.add_edge(a, b, weight=1, event_ids=[event['event_id']])
    return net


def average_positions(g: nx.MultiDiGraph, team: str, start: int = 0, end: int = 90) -> dict[str, dict[str, float]]:
    """Each player's average on-ball position in the window, for drawing the pass network."""
    sums: dict[str, list[float]] = {}
    for node, data in g.nodes(data=True):
        if data['kind'] != 'Event' or data['team_id'] != team or not start <= data['minute'] < end \
                or data['event_type'] not in ON_BALL_TYPES:
            continue
        actor = next(p for p, _, k in g.in_edges(node, keys=True) if k == 'PERFORMED').removeprefix('player:')
        entry = sums.setdefault(actor, [0.0, 0.0, 0])
        entry[0] += data['x']
        entry[1] += data['y']
        entry[2] += 1
    return {p: {'x': round(x / n, 1), 'y': round(y / n, 1), 'actions': n} for p, (x, y, n) in sums.items()}


PROGRESSIVE_M = 10.0  # a pass that moves the ball at least 10 m towards the opponent's goal


def network_detail(g: nx.MultiDiGraph, team: str, start: int = 0, end: int = 90) -> dict[str, Any]:
    """The pass network for exploring: each lane's passes, direction and forward progress, each
    player's passes made and received, and whole-network measures. Every lane keeps its evidence."""
    lanes: dict[tuple[str, str], dict[str, Any]] = {}
    for u, v, key in g.edges(keys=True):
        if key != 'RECEIVED_BY':
            continue
        event = g.nodes[u]
        if event['team_id'] != team or not start <= event['minute'] < end:
            continue
        passer = next(p for p, _, k in g.in_edges(u, keys=True) if k == 'PERFORMED').removeprefix('player:')
        lane = lanes.setdefault((passer, v.removeprefix('player:')), {'passes': 0, 'progressive': 0, 'gain': 0.0,
                                                                     'minutes': [], 'event_ids': []})
        gain = ((event.get('end_x') if event.get('end_x') is not None else event['x']) - event['x']) * 1.05
        lane['passes'] += 1
        lane['progressive'] += gain >= PROGRESSIVE_M
        lane['gain'] += gain
        lane['minutes'].append(event['minute'])
        lane['event_ids'].append(event['event_id'])
    edges = [{'from': a, 'to': b, 'passes': d['passes'], 'progressive': d['progressive'],
              'gain_m': round(d['gain'] / d['passes'], 1), 'minutes': [min(d['minutes']), max(d['minutes'])],
              'event_ids': d['event_ids']} for (a, b), d in sorted(lanes.items())]
    total = sum(e['passes'] for e in edges)
    players: dict[str, dict[str, Any]] = {}
    for e in edges:
        for pid, field in ((e['from'], 'made'), (e['to'], 'received')):
            p = players.setdefault(pid, {'shirt': PLAYERS[pid].shirt if pid in PLAYERS else None,
                                         'made': 0, 'received': 0, 'progressive': 0})
            p[field] += e['passes']
        players[e['from']]['progressive'] += e['progressive']
    used = {(e['from'], e['to']) for e in edges}
    n = len(players)
    involvement = sorted((p['made'] + p['received'] for p in players.values()), reverse=True)
    network = {'players': n, 'lanes': len(edges),
               'density': round(len(used) / (n * (n - 1)), 3) if n > 1 else 0.0,
               'two_way': round(sum((b, a) in used for a, b in used) / len(used), 3) if used else 0.0,
               'top_three_share': round(sum(involvement[:3]) / (2 * total), 3) if total else 0.0,
               'progressive_share': round(sum(e['progressive'] for e in edges) / total, 3) if total else 0.0}
    return {'edges': edges, 'player_stats': players, 'network': network}


def network_roles(g: nx.MultiDiGraph, team: str, start: int = 0, end: int = 90) -> dict[str, Any]:
    """Network roles computed on the pass network read back out of the knowledge graph."""
    return roles(passing_graph(g, team, start, end), team, start, end, name)


def xg_chain(g: nx.MultiDiGraph, team: str) -> list[dict[str, Any]]:
    """xG chain: total xG of possessions a player touched. xG build-up excludes the shot and
    the assist, crediting the work before them."""
    chain: dict[str, float] = defaultdict(float)
    buildup: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[str]] = defaultdict(list)
    for node, data in g.nodes(data=True):
        if data['kind'] != 'Possession' or data['team_id'] != team or not data['xg']:
            continue
        sequence = sorted((u for u, _, k in g.in_edges(node, keys=True) if k == 'IN_POSSESSION'),
                          key=lambda n: g.nodes[n]['clock'])
        actors, final = [], set()
        for event_node in sequence:
            event = g.nodes[event_node]
            if event['team_id'] != team:
                continue
            actor = next(p for p, _, k in g.in_edges(event_node, keys=True) if k == 'PERFORMED').removeprefix('player:')
            actors.append(actor)
            if event['event_type'] == 'shot':
                final.add(actor)
                if len(actors) >= 2:
                    final.add(actors[-2])  # the pass into the shooter
        for actor in set(actors):
            chain[actor] += data['xg']
            evidence[actor].append(data['possession_id'])
            if actor not in final:
                buildup[actor] += data['xg']
    return sorted(({'player_id': p, 'name': name(p), 'xg_chain': round(v, 2), 'xg_buildup': round(buildup[p], 2),
                    'possessions': evidence[p]} for p, v in chain.items()),
                  key=lambda r: (-r['xg_chain'], r['player_id']))


def buildup_chains(g: nx.MultiDiGraph, team: str, limit: int = 5) -> list[dict[str, Any]]:
    """Possessions that ended in a shot or goal, as the ordered chain of players involved."""
    chains = []
    for node, data in g.nodes(data=True):
        if data['kind'] != 'Possession' or data['team_id'] != team or data['ended_with'] == 'turnover':
            continue
        sequence = sorted((u for u, _, k in g.in_edges(node, keys=True) if k == 'IN_POSSESSION'),
                          key=lambda n: g.nodes[n]['clock'])
        steps = []
        for event_node in sequence:
            event = g.nodes[event_node]
            if event['team_id'] != team or event['event_type'] not in ON_BALL_TYPES:
                continue
            actor = next(p for p, _, k in g.in_edges(event_node, keys=True) if k == 'PERFORMED').removeprefix('player:')
            steps.append({'event_id': event['event_id'], 'player_id': actor, 'name': name(actor),
                          'event_type': event['event_type'], 'outcome': event['outcome'], 'clock': event['clock'],
                          'pass_difficulty': event['pass_difficulty'], 'speed_kmh': event['speed_kmh']})
        chains.append({'possession_id': data['possession_id'], 'ended_with': data['ended_with'], 'xg': data['xg'],
                       'start': data['start'], 'end': data['end'], 'passes': data['passes'], 'steps': steps})
    chains.sort(key=lambda c: (c['ended_with'] != 'goal', -c['xg'], c['start']))
    return chains[:limit]


def why(g: nx.MultiDiGraph, moment_id: str) -> dict[str, Any]:
    """Why a moment matters: its facts, evidence events, the build-up that led to it, the
    players involved with their network role at the time, and what came just before."""
    node = f'moment:{moment_id}'
    if node not in g:
        raise KeyError(moment_id)
    m = g.nodes[node]
    evidence = sorted((u for u, _, k in g.in_edges(node, keys=True) if k == 'EVIDENCES'),
                      key=lambda n: g.nodes[n]['clock'])
    players = [v.removeprefix('player:') for _, v, k in g.out_edges(node, keys=True) if k == 'INVOLVES']
    chain = None
    if evidence and m['moment_kind'] in {'goal', 'big_chance'}:
        shot = next((e for e in evidence if g.nodes[e]['event_type'] == 'shot'), evidence[-1])
        possession = next((v for _, v, k in g.out_edges(shot, keys=True) if k == 'IN_POSSESSION'), None)
        if possession:
            chain = next((c for c in buildup_chains(g, m['team_id'], limit=500)
                          if c['possession_id'] == g.nodes[possession]['possession_id']), None)
    roles = {}
    if m['team_id'] and players:
        minute = m['clock'] // 60 + 1
        window = network_roles(g, m['team_id'], max(0, minute - 15), minute)
        for pid in players:
            entry = next((p for p in window['players'] if p['player_id'] == pid), None)
            roles[pid] = {'name': name(pid), **({k: entry[k] for k in ('pass_share', 'betweenness', 'pagerank')}
                                                if entry else {}),
                          'is_hub': window.get('hub') == pid, 'is_connector': window.get('connector') == pid}
    before = [g.nodes[u] for u, _, k in g.in_edges(node, keys=True) if k == 'FOLLOWS']
    return {'moment_id': moment_id, 'kind': m['moment_kind'], 'clock': m['clock'], 'why': m['why'],
            'facts': m['facts'], 'evidence_event_ids': [g.nodes[e]['event_id'] for e in evidence],
            'buildup': chain, 'players': roles,
            'previous_moment': {'moment_id': before[0]['moment_id'], 'kind': before[0]['moment_kind'],
                                'clock': before[0]['clock']} if before else None,
            'path': ['Event -EVIDENCES-> Moment', 'Event -IN_POSSESSION-> Possession', 'Moment -INVOLVES-> Player',
                     'Player -PASSED_TO-> Player', 'Moment -FOLLOWS-> Moment']}


def impact(g: nx.MultiDiGraph, event_id: str) -> dict[str, list[str]]:
    """Every output that depends on an event: moments it evidences and claims it supports.
    Overlays and recaps are built from these, so they are listed through them."""
    node = f'event:{event_id}'
    if node not in g:
        return {'moments': [], 'claims': [], 'overlays': [], 'recaps': []}
    moments = sorted(g.nodes[v]['moment_id'] for _, v, k in g.out_edges(node, keys=True) if k == 'EVIDENCES')
    claims = sorted(g.nodes[v]['claim_id'] for _, v, k in g.out_edges(node, keys=True) if k == 'SUPPORTS')
    return {'moments': moments, 'claims': claims,
            'overlays': [f'ovl-{m}' for m in moments],
            'recaps': ['recap'] if claims or any(m.startswith('goal:') for m in moments) else []}


def timeline(g: nx.MultiDiGraph, team: str | None = None) -> list[dict[str, Any]]:
    """The developing story: moments in order along FOLLOWS, with the running score."""
    start = [n for n, d in g.nodes(data=True) if d['kind'] == 'Moment'
             and not any(k == 'FOLLOWS' for _, _, k in g.in_edges(n, keys=True))]
    out, node, score = [], start[0] if start else None, {'home': 0, 'away': 0}
    while node is not None:
        m = g.nodes[node]
        if m['moment_kind'] == 'goal':
            score = {'home': m['facts']['home'], 'away': m['facts']['away']}
        if team is None or m['team_id'] == team:
            out.append({'moment_id': m['moment_id'], 'kind': m['moment_kind'], 'clock': m['clock'],
                        'team_id': m['team_id'], 'score': dict(score)})
        node = next((v for _, v, k in g.out_edges(node, keys=True) if k == 'FOLLOWS'), None)
    return out


def summary(g: nx.MultiDiGraph) -> dict[str, Any]:
    kinds = defaultdict(int)
    for _, d in g.nodes(data=True):
        kinds[d['kind']] += 1
    relations = defaultdict(int)
    for _, _, k in g.edges(keys=True):
        relations[k] += 1
    return {'nodes': dict(sorted(kinds.items())), 'relationships': dict(sorted(relations.items()))}


_GRAPHS: dict[tuple, nx.MultiDiGraph] = {}


def match_graph(seed: int, minute: int) -> tuple[nx.MultiDiGraph, list[Event], dict[str, Any]]:
    """The knowledge graph for the current (corrected) source at `minute`, cached per state version."""
    from .foundation import repository
    stream, version, source = repository().snapshot(seed)
    key = (stream, version, seed, minute)
    if key not in _GRAPHS:
        if len(_GRAPHS) >= 64:
            _GRAPHS.pop(next(iter(_GRAPHS)))
        _GRAPHS[key] = build_graph(source, seed, minute, stream, version)
    return _GRAPHS[key], source, {'match_id': stream, 'state_version': version, 'minute': minute}


def _property(value: Any) -> Any:
    """Bolt properties are scalars or flat lists; nested values are stored as JSON text."""
    import json
    if isinstance(value, dict) or (isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return value


def projection_rows(g: nx.MultiDiGraph) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Node rows per label and relationship rows per type, for the database projection."""
    nodes: dict[str, list[dict]] = defaultdict(list)
    for node, data in g.nodes(data=True):
        props = {k: _property(v) for k, v in data.items() if v is not None}
        nodes[data['kind']].append({'key': node, 'props': props})
    edges: dict[str, list[dict]] = defaultdict(list)
    for u, v, key, data in g.edges(keys=True, data=True):
        edges[key].append({'a': u, 'b': v, 'props': {k: _property(x) for k, x in data.items() if x is not None}})
    return dict(nodes), dict(edges)
