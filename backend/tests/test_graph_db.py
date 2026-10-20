"""Real graph-database tests: the knowledge graph projected into Memgraph and Neo4j must answer
the same as NetworkX, and replaying the projection must not duplicate anything.

Skipped unless GRAPH_TEST_TARGETS names running databases, for example
GRAPH_TEST_TARGETS="memgraph=bolt://memgraph:7687,neo4j=bolt://neo4j:7687" with
GRAPH_TEST_NEO4J_PASSWORD set. CI runs them in Azure Container Registry Tasks (graph-db-tests.yaml).
"""
import os
import time
from dataclasses import replace

import pytest

from app.core import generate_match
from app.knowledge import build_graph, impact, network_roles, passing_graph, summary, timeline, why, xg_chain

TARGETS = dict(t.split('=', 1) for t in os.getenv('GRAPH_TEST_TARGETS', '').split(',') if '=' in t)
pytestmark = pytest.mark.skipif(not TARGETS, reason='GRAPH_TEST_TARGETS not set; no graph database available')
SEED = 20261020


def connect(backend: str, uri: str):
    from app.graph.repository import BoltGraphRepository
    user, password = ('neo4j', os.getenv('GRAPH_TEST_NEO4J_PASSWORD', '')) if backend == 'neo4j' else ('', '')
    deadline = time.monotonic() + 120
    while True:  # a freshly started container takes a few seconds to accept connections
        try:
            repo = BoltGraphRepository(backend, uri, user, password)
            repo.health()
            return repo
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(2)


@pytest.fixture(scope='module', params=sorted(TARGETS))
def db(request):
    repo = connect(request.param, TARGETS[request.param])
    yield repo
    repo.close()


@pytest.fixture(scope='module')
def events():
    return generate_match(SEED)


@pytest.fixture(scope='module')
def graph(events):
    return build_graph(events, SEED, 90, 'db-test-match')


@pytest.fixture(scope='module')
def projected(db, graph):
    db.project_knowledge(graph)
    return db


def test_counts_match_networkx(projected, graph):
    assert projected.kg_summary('db-test-match') == summary(graph)


def test_projection_is_idempotent(projected, graph):
    projected.project_knowledge(graph)
    projected.project_knowledge(graph)
    assert projected.kg_summary('db-test-match') == summary(graph)


def test_pass_lanes_match_networkx(projected, graph):
    for team in ('home', 'away'):
        for start, end in ((0, 90), (45, 60)):
            expected = {(u, v): (d['weight'], sorted(d['event_ids']))
                        for u, v, d in passing_graph(graph, team, start, end).edges(data=True)}
            stored = {(r['source'], r['target']): (r['weight'], sorted(r['event_ids']))
                      for r in projected.kg_pass_lanes('db-test-match', team, start, end)}
            assert stored == expected
            assert sum(w for w, _ in stored.values()) == network_roles(graph, team, start, end)['completed_passes']


def test_moment_evidence_matches_networkx(projected, graph):
    moments = [d['moment_id'] for _, d in graph.nodes(data=True) if d['kind'] == 'Moment']
    for moment_id in moments[:40]:
        assert projected.kg_evidence('db-test-match', moment_id) == why(graph, moment_id)['evidence_event_ids']


def test_impact_matches_networkx(projected, graph, events):
    for e in [e for e in events if e.outcome == 'goal'] + events[:50]:
        expected = impact(graph, e.event_id)
        stored = projected.kg_impact('db-test-match', e.event_id)
        assert stored == {'moments': expected['moments'], 'claims': expected['claims']}


def test_xg_chain_matches_networkx(projected, graph):
    for team in ('home', 'away'):
        expected = {r['player_id']: r['xg_chain'] for r in xg_chain(graph, team)}
        stored = {r['player_id']: r['xg_chain'] for r in projected.kg_xg_chain('db-test-match', team)}
        assert stored.keys() == expected.keys()
        assert all(abs(stored[p] - expected[p]) <= 0.011 for p in expected)


def test_timeline_order_matches_networkx(projected, graph):
    assert projected.kg_timeline('db-test-match') == [m['moment_id'] for m in timeline(graph)]


def test_correction_replaces_projection_and_leaves_other_matches(db, events, graph):
    other = build_graph(generate_match(7), 7, 90, 'db-other-match')
    db.project_knowledge(other)
    goal = next(e for e in events if e.outcome == 'goal')
    corrected = build_graph([replace(e, outcome='saved') if e.event_id == goal.event_id else e for e in events],
                            SEED, 90, 'db-test-match', state_version=2)
    db.project_knowledge(corrected)
    assert db.kg_summary('db-test-match') == summary(corrected)
    assert db.kg_summary('db-other-match') == summary(other)
    assert not any(m.startswith('goal:') for m in db.kg_impact('db-test-match', goal.event_id)['moments'])
    db.project_knowledge(graph)


def test_event_projection_does_not_remove_knowledge_graph(db, events, graph):
    db.project_knowledge(graph)
    db.upsert_events(events)
    assert db.kg_summary('db-test-match') == summary(graph)
    assert len(db.read_events(events[0].match_id)) == len(events)
