"""Local-only research dataset adapters; source files are not deployment assets."""
from functools import lru_cache
from pathlib import Path
import json
import networkx as nx
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

def research_enabled() -> None:
    """Real-data research views are off by default: the product itself uses synthetic data only."""
    if os.getenv('MATCHMIND_RESEARCH_ENABLED', 'false').lower() != 'true':
        raise HTTPException(404, 'Research datasets are disabled. Set MATCHMIND_RESEARCH_ENABLED=true locally.')


router = APIRouter(prefix='/api/research', dependencies=[Depends(research_enabled)])
ROOT = Path(__file__).resolve().parents[1] / 'data/research'

def dataset_file(provider, name):
    path = ROOT / provider / name
    if not path.is_file():
        raise HTTPException(503, 'Local research sample missing. Run python tools/import-research-data.py.')
    return path

@router.get('/metrica/{resource}')
def metrica_resource(resource: str):
    names = {'frames': 'frames.json', 'match': 'match.json', 'events': 'events.json',
             'terms': 'README.md', 'provenance': 'provenance.json'}
    if resource not in names:
        raise HTTPException(404, 'Unknown research resource')
    return FileResponse(dataset_file('metrica', names[resource]))

@router.get('/statsbomb/logo')
def statsbomb_logo():
    return FileResponse(dataset_file('statsbomb', 'logo.png'))

@router.get('/statsbomb/terms')
def statsbomb_terms():
    return FileResponse(dataset_file('statsbomb', 'LICENSE.pdf'))

@lru_cache(maxsize=1)
def statsbomb_source():
    return json.loads(dataset_file('statsbomb', 'events.json').read_text(encoding='utf-8'))

def analyze_statsbomb(events, event_limit):
    visible = events[:event_limit]
    graph = nx.DiGraph()
    teams = {779: {'name': 'Argentina', 'passes': 0, 'completed': 0, 'shots': 0, 'goals': 0, 'xg': 0., 'shootout_goals': 0},
             771: {'name': 'France', 'passes': 0, 'completed': 0, 'shots': 0, 'goals': 0, 'xg': 0., 'shootout_goals': 0}}
    normalized = []
    positions = {}
    for e in visible:
        team_id = e.get('team', {}).get('id')
        if team_id not in teams:
            continue
        team = teams[team_id]
        kind = e['type']['name']
        player = e.get('player', {})
        period = e['period']
        if period == 5:
            if kind == 'Shot' and e['shot']['outcome']['name'] == 'Goal':
                team['shootout_goals'] += 1
            continue
        loc = e.get('location')
        if player and loc:
            positions.setdefault(player['id'], []).append([loc[0]/120*100, loc[1]/80*100])
            graph.add_node(player['id'], name=player['name'], team=team['name'])
        outcome = ''
        recipient = ''
        end = None
        if kind == 'Pass':
            p = e['pass']
            team['passes'] += 1
            complete = 'outcome' not in p
            team['completed'] += int(complete)
            outcome = 'Complete' if complete else p['outcome']['name']
            receiver = p.get('recipient')
            recipient = receiver['name'] if receiver else ''
            end = p.get('end_location')
            if complete and receiver and player:
                graph.add_node(receiver['id'], name=receiver['name'], team=team['name'])
                u, v = player['id'], receiver['id']
                if not graph.has_edge(u, v):
                    graph.add_edge(u, v, weight=0, evidence=[])
                graph[u][v]['weight'] += 1
                graph[u][v]['evidence'].append(e['id'])
        elif kind == 'Shot':
            shot = e['shot']
            team['shots'] += 1
            team['xg'] += shot.get('statsbomb_xg', 0.)
            outcome = shot['outcome']['name']
            team['goals'] += int(outcome == 'Goal')
            end = shot.get('end_location')
        elif kind == 'Own Goal Against':
            teams[771 if team_id == 779 else 779]['goals'] += 1
        if kind in ['Pass', 'Shot', 'Own Goal Against']:
            normalized.append({'id': e['id'], 'index': e['index'], 'period': period,
                               'minute': e['minute'], 'second': e['second'], 'type': kind,
                               'team': team['name'], 'player': player.get('name', ''),
                               'recipient': recipient, 'outcome': outcome,
                               'xg': e.get('shot', {}).get('statsbomb_xg'),
                               'start': [loc[0]/120*100, loc[1]/80*100] if loc else None,
                               'end': [end[0]/120*100, end[1]/80*100] if end else None})
    nodes = []
    for pid, attrs in graph.nodes(data=True):
        points = positions.get(pid, [])
        if points:
            nodes.append({'id': pid, **attrs, 'x': sum(p[0] for p in points)/len(points),
                          'y': sum(p[1] for p in points)/len(points),
                          'involvement': graph.degree(pid, weight='weight')})
    edges = [{'from': u, 'to': v, 'weight': a['weight'], 'evidence': a['evidence'],
              'from_name': graph.nodes[u]['name'], 'to_name': graph.nodes[v]['name'],
              'team': graph.nodes[u]['team']} for u, v, a in graph.edges(data=True)]
    return {'provider': 'StatsBomb', 'match': 'Argentina v France', 'date': '18 December 2022',
            'competition': 'World Cup final', 'match_id': 3869685,
            'total_events': len(events), 'events_processed': len(visible),
            'teams': list(teams.values()), 'events': normalized,
            'nodes': nodes, 'edges': sorted(edges, key=lambda a: -a['weight']),
            'engine': 'NetworkX directed weighted passing graph',
            'clock': {k: visible[-1][k] for k in ['period', 'minute', 'second']} if visible else None}

@router.get('/statsbomb')
def statsbomb_analysis(event_limit: int = Query(4407, ge=0, le=10000)):
    return analyze_statsbomb(statsbomb_source(), event_limit)
