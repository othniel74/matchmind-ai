"""Pure NetworkX analytics, independent of Memgraph/Neo4j availability."""
from __future__ import annotations
from collections import defaultdict
import networkx as nx
from ..core import Event


def passing_graph(events: list[Event], team: str, start: int = 0, end: int = 90) -> nx.DiGraph:
    """Use explicit synthetic recipients, with a labeled legacy fallback.

    Events without recipients may use the next same-possession actor as a proxy.
    Neither generated recipients nor proxies are real match observations.
    """
    method = 'explicit_recipient' if all(e.recipient_player_id for e in events
        if e.event_type == 'pass' and e.outcome == 'success') else 'mixed_recipient_proxy'
    graph = nx.DiGraph(team=team, start=start, end=end, receiver_method=method)
    ordered = sorted(events, key=lambda e: e.sequence)
    for i, event in enumerate(ordered):
        if not (start <= event.minute < end and event.team_id == team and
                event.event_type == 'pass' and event.outcome == 'success'):
            continue
        target = event.recipient_player_id
        if target is None:
            if i + 1 >= len(ordered):
                continue
            successor = ordered[i+1]
            if (successor.team_id != team or successor.possession_id != event.possession_id or
                    successor.player_id == event.player_id or successor.minute >= end):
                continue
            target = successor.player_id
        source = event.player_id
        if graph.has_edge(source, target):
            edge = graph[source][target]
            edge['weight'] += 1
            edge['event_ids'].append(event.event_id)
        else:
            graph.add_edge(source, target, weight=1, event_ids=[event.event_id])
    return graph


def graph_metrics(graph: nx.DiGraph) -> dict:
    if not graph.number_of_nodes():
        return {'nodes': 0, 'edges': 0, 'passes': 0, 'density': 0.0, 'weighted_degree': {}, 'betweenness': {}, 'components': [], 'receiver_method': graph.graph.get('receiver_method', 'unknown')}
    weighted = {n: int(graph.in_degree(n, weight='weight') + graph.out_degree(n, weight='weight')) for n in graph.nodes}
    centrality = nx.betweenness_centrality(graph, weight=None, normalized=True)
    return {'nodes': graph.number_of_nodes(), 'edges': graph.number_of_edges(),
            'passes': sum(d['weight'] for _, _, d in graph.edges(data=True)),
            'density': round(nx.density(graph), 6),
            'weighted_degree': dict(sorted(weighted.items())),
            'betweenness': {k: round(v, 6) for k, v in sorted(centrality.items())},
            'components': [sorted(c) for c in sorted(nx.weakly_connected_components(graph), key=lambda c: (-len(c), sorted(c)))],
            'receiver_method': graph.graph.get('receiver_method', 'unknown')}


def network_snapshot(events: list[Event], team: str, start: int, end: int) -> dict:
    graph = passing_graph(events, team, start, end)
    edges = [{'source': u, 'target': v, 'weight': d['weight'], 'event_ids': d['event_ids']}
             for u, v, d in sorted(graph.edges(data=True))]
    return {'team': team, 'start_minute': start, 'end_minute': end,
            'metrics': graph_metrics(graph), 'nodes': sorted(graph.nodes), 'edges': edges,
            'disclaimer': 'Synthetic generated recipients are used when supplied; legacy events use next-actor proxies. These are not real match observations.'}


def compare_windows(events: list[Event], team: str, minute: int, window: int = 10) -> dict:
    if not 2 * window <= minute <= 90:
        raise ValueError('minute must cover two full windows')
    previous = network_snapshot(events, team, minute - 2 * window, minute - window)
    current = network_snapshot(events, team, minute - window, minute)
    return {'team': team, 'minute': minute, 'previous': previous, 'current': current,
            'delta_edges': current['metrics']['edges'] - previous['metrics']['edges'],
            'delta_passes': current['metrics']['passes'] - previous['metrics']['passes'],
            'delta_density': round(current['metrics']['density'] - previous['metrics']['density'], 6),
            'interpretation': 'Observed change in proxy passing connectivity; not proof of tactical causation.'}


def pagerank(net: nx.DiGraph, damping: float = 0.85, iterations: int = 100, tolerance: float = 1e-10) -> dict:
    """Weighted PageRank by power iteration (networkx's version needs numpy/scipy, which this
    service does not otherwise use). Players who pass to nobody spread their rank evenly."""
    nodes = list(net)
    if not nodes:
        return {}
    n = len(nodes)
    rank = {v: 1 / n for v in nodes}
    out_weight = {v: sum(d['weight'] for _, _, d in net.out_edges(v, data=True)) for v in nodes}
    for _ in range(iterations):
        dangling = damping * sum(rank[v] for v in nodes if not out_weight[v]) / n
        new = {v: (1 - damping) / n + dangling for v in nodes}
        for u, v, d in net.edges(data=True):
            new[v] += damping * rank[u] * d['weight'] / out_weight[u]
        if sum(abs(new[v] - rank[v]) for v in nodes) < tolerance:
            return new
        rank = new
    return rank


def roles(net: nx.DiGraph, team: str, start: int, end: int, names=lambda p: p) -> dict:
    """Who a pass network runs through: hub (most passes made or received), key connector
    (betweenness over pass-frequency distances), PageRank, and the strongest passing lanes."""
    active = [n for n in net if net.degree(n, weight='weight') > 0]
    sub = net.subgraph(active).copy()
    total = sum(d['weight'] for _, _, d in sub.edges(data=True))
    if not total:
        return {'team_id': team, 'window': [start, end], 'completed_passes': 0, 'players': [], 'lanes': [],
                'hub': None, 'connector': None}
    distance = nx.DiGraph()
    distance.add_edges_from((u, v, {'cost': 1 / d['weight']}) for u, v, d in sub.edges(data=True))
    betweenness = nx.betweenness_centrality(distance, weight='cost', normalized=True)
    rank = pagerank(sub)
    players = []
    for pid in active:
        involvement = sub.degree(pid, weight='weight')
        players.append({'player_id': pid, 'name': names(pid), 'involvement': involvement,
                        'pass_share': round(involvement / total, 3),
                        'betweenness': round(betweenness.get(pid, 0.0), 3), 'pagerank': round(rank[pid], 3)})
    players.sort(key=lambda p: (-p['pagerank'], p['player_id']))
    lanes = sorted(({'from': u, 'to': v, 'from_name': names(u), 'to_name': names(v), 'passes': d['weight'],
                     'event_ids': d['event_ids']} for u, v, d in sub.edges(data=True)),
                   key=lambda l: (-l['passes'], l['from'], l['to']))[:5]
    return {'team_id': team, 'window': [start, end], 'completed_passes': total, 'players': players,
            'hub': max(players, key=lambda p: (p['involvement'], p['player_id']))['player_id'],
            'connector': max(players, key=lambda p: (p['betweenness'], p['player_id']))['player_id'],
            'lanes': lanes,
            'definitions': {'hub': 'most completed passes made or received',
                            'connector': 'highest betweenness on the pass network (most shortest routes run through the player)',
                            'pagerank': 'importance weighted by who passes to the player'}}
