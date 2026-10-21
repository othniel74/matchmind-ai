from dataclasses import replace

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.ask import keyword_intent, parse_intent, answer
from app.core import generate_match
from app.graph.analytics import pagerank, passing_graph as event_passing_graph, roles
from app.knowledge import (NODE_KINDS, RELATIONS, build_graph, buildup_chains, impact, network_roles,
                           passing_graph, projection_rows, summary, timeline, why, xg_chain)
from app.main import app

SEED = 20261020


@pytest.fixture(scope='module')
def events():
    return generate_match(SEED)


@pytest.fixture(scope='module')
def graph(events):
    return build_graph(events, SEED, 90, 'test-match')


def test_graph_holds_every_kind_and_relation(graph):
    counts = summary(graph)
    assert set(counts['nodes']) == set(NODE_KINDS)
    assert set(counts['relationships']) == set(RELATIONS)
    assert counts['nodes']['Team'] == 2 and counts['nodes']['Player'] == 32


def test_graph_is_time_scoped(events):
    g = build_graph(events, SEED, 30, 'test-match')
    assert all(d['minute'] < 30 for _, d in g.nodes(data=True) if d['kind'] == 'Event')
    assert all(d['clock'] <= 30 * 60 for _, d in g.nodes(data=True) if d['kind'] == 'Moment')


def test_pass_network_read_from_graph_matches_event_stream(events, graph):
    for team in ('home', 'away'):
        from_graph = passing_graph(graph, team, 20, 60)
        from_events = event_passing_graph([e for e in events if e.minute < 90], team, 20, 60)
        assert {(u, v, d['weight']) for u, v, d in from_graph.edges(data=True)} == \
               {(u, v, d['weight']) for u, v, d in from_events.edges(data=True)}


def test_roles_name_both_teams_with_hub_and_connector(graph):
    for team in ('home', 'away'):
        r = network_roles(graph, team, 0, 90)
        assert r['hub'] and r['connector'] and r['players'][0]['name'] != r['players'][0]['player_id']
        assert sum(p['involvement'] for p in r['players']) == 2 * r['completed_passes']
        assert abs(sum(p['pagerank'] for p in r['players']) - 1) < 0.02


def test_pagerank_matches_reference_on_a_cycle():
    net = nx.DiGraph([(1, 2), (2, 3), (3, 1)])
    nx.set_edge_attributes(net, 1, 'weight')
    assert all(abs(v - 1 / 3) < 1e-6 for v in pagerank(net).values())


def test_empty_window_has_no_roles():
    assert roles(nx.DiGraph(), 'home', 0, 5)['hub'] is None


def test_xg_chain_credits_every_player_in_shot_possessions(graph):
    for team in ('home', 'away'):
        rows = xg_chain(graph, team)
        assert rows and all(r['xg_buildup'] <= r['xg_chain'] for r in rows)
        top = rows[0]
        for pid in top['possessions']:
            assert graph.nodes[f'possession:{pid}']['xg'] > 0


def test_buildup_chains_put_goals_first(graph):
    chains = buildup_chains(graph, 'away', limit=3)
    assert chains[0]['ended_with'] == 'goal' and chains[0]['steps'][-1]['event_type'] == 'shot'


def test_why_explains_a_goal_with_evidence_buildup_and_roles(graph):
    goal = next(d['moment_id'] for _, d in graph.nodes(data=True) if d['kind'] == 'Moment' and d['moment_kind'] == 'goal')
    result = why(graph, goal)
    assert result['evidence_event_ids'] and result['buildup']['ended_with'] == 'goal'
    assert set(result['evidence_event_ids']) <= {s['event_id'] for s in result['buildup']['steps']}
    assert result['players'] and all('is_connector' in r for r in result['players'].values())
    with pytest.raises(KeyError):
        why(graph, 'missing')


def test_timeline_follows_story_with_running_score(graph):
    story = timeline(graph)
    assert [m['clock'] for m in story] == sorted(m['clock'] for m in story)
    assert story[-1]['score'] == {'home': 2, 'away': 3}


def test_impact_reaches_moments_claims_overlays_and_recap(graph):
    goal = next(d for _, d in graph.nodes(data=True) if d['kind'] == 'Event' and d['outcome'] == 'goal')
    result = impact(graph, goal['event_id'])
    assert any(m.startswith('goal:') for m in result['moments'])
    assert result['claims'] and result['recaps'] == ['recap']
    assert result['overlays'] == [f'ovl-{m}' for m in result['moments']]
    assert impact(graph, 'missing') == {'moments': [], 'claims': [], 'overlays': [], 'recaps': []}


def test_correction_impact_reports_changed_outputs(events):
    from app.foundation import knowledge_impact
    goal = next(e for e in events if e.outcome == 'goal')
    assist = max((e for e in events if e.event_type == 'pass' and e.outcome == 'success'
                  and e.possession_id == goal.possession_id and e.sequence < goal.sequence), key=lambda e: e.sequence)
    result = knowledge_impact(events, replace(assist, outcome='failed', recipient_player_id=None), SEED, 's', 1)
    assert any(m.startswith('goal:') for m in result['depends_on_event']['moments'])
    assert result['changes']['moments']['changed'] or result['changes']['moments']['removed']
    assert result['recaps_need_refresh']


def test_projection_rows_are_bolt_safe(graph):
    nodes, edges = projection_rows(graph)
    assert sum(map(len, nodes.values())) == graph.number_of_nodes()
    assert sum(map(len, edges.values())) == graph.number_of_edges()
    for rows in nodes.values():
        for row in rows:
            for value in row['props'].values():
                assert value is not None and not isinstance(value, dict)
                assert not (isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value))


@pytest.mark.parametrize('question,intent', [
    ('What is the score?', 'score'), ('Who scored?', 'scorers'), ('¿Quién marcó?', 'scorers'),
    ('Qui a marqué ?', 'scorers'), ('Wer hat die meisten Schüsse?', 'stat'), ('ما النتيجة؟', 'score'),
    ('Why did Merridge score?', 'why_moment'), ("Who is Merridge's key player?", 'key_player'),
    ('Show the build-up to the goal', 'buildup'), ('Who has momentum?', 'momentum'),
    ('How is Moreau-Diallo playing?', 'player'), ('What is the weather?', 'unsupported')])
def test_keyword_routing(question, intent):
    assert keyword_intent(question)['intent'] == intent


def test_model_routing_is_validated():
    assert parse_intent('{"intent": "stat", "metric": "xg", "team": "home"}', 'q')['metric'] == 'xg'
    assert parse_intent('{"intent": "invent_facts"}', 'who scored')['intent'] == 'scorers'
    assert parse_intent('not json', 'what is the weather')['intent'] == 'unsupported'
    assert parse_intent('{"intent": "unsupported"}', 'who scored?')['intent'] == 'scorers'
    assert parse_intent('{"intent": "unsupported"}', 'what is the weather')['intent'] == 'unsupported'
    assert parse_intent('{"intent": "stat", "metric": "made_up", "team": "both"}', 'q')['metric'] is None


def test_answers_cite_evidence_and_never_use_the_future(events):
    g = build_graph(events, SEED, 30, 'test-match')
    result = answer(g, events, SEED, 30, keyword_intent('who scored'), 'en')
    later = {e.event_id for e in events if e.minute >= 30}
    assert result['evidence_event_ids'] and not set(result['evidence_event_ids']) & later
    unsupported = answer(g, events, SEED, 30, keyword_intent('tell me a joke about the weather'), 'es')
    assert not unsupported['supported'] and unsupported['evidence_event_ids'] == []


def test_graph_api():
    client = TestClient(app)
    knowledge = client.get('/api/graph/knowledge').json()
    assert knowledge['database']['status'] == 'disabled' and knowledge['networkx']['nodes']['Moment'] > 0
    roles_ = client.get('/api/graph/roles?minute=67').json()
    assert set(roles_['teams']) == {'home', 'away'}
    assert client.get('/api/graph/xg-chain?team=away').json()['teams']['away'][0]['name']
    story = client.get('/api/graph/timeline?minute=60&language=ar').json()['timeline']
    assert story and story[0]['direction'] == 'rtl'
    goal = next(m for m in story if m['kind'] == 'goal')
    assert client.get(f"/api/graph/why?moment_id={goal['moment_id']}&minute=60").json()['source'] == 'networkx'
    assert client.get('/api/graph/why?moment_id=nope').status_code == 404
    assert client.get('/api/graph/buildup?limit=1').status_code == 200
    assert client.get('/api/graph/impact?event_id=evt-00116').json()['moments']
    asked = client.get('/api/ask?q=who%20scored&minute=60&language=pt').json()
    assert asked['router'] == 'keywords' and asked['answer'].startswith('Gols')


def test_experience_focus_card_has_network_role():
    body = TestClient(app).get('/api/experience?minute=67&focus_player=away-10').json()
    role = body['focus']['network_role']
    assert role['match']['is_hub'] and role['match']['top_partners']


def test_fans_see_speed_records_not_every_speed_tag(events):
    from app.experience import Profile, experience
    fan = experience(events, SEED, 30, Profile(audience='fan'))['moments']
    analyst = experience(events, SEED, 30, Profile(audience='analyst'))['moments']
    speeds = sorted((m for m in fan if m['kind'] == 'top_speed'), key=lambda m: m['clock_seconds'])
    values = [m['facts']['value'] for m in speeds]
    assert values == sorted(values) and len(set(values)) == len(values)  # each one a new match high
    assert len(speeds) < sum(m['kind'] == 'top_speed' for m in analyst)
    mine = experience(events, SEED, 30, Profile(audience='fan', players=('away-05',)))['moments']
    assert any(m['kind'] == 'top_speed' and 'away-05' in m['player_ids'] for m in mine)


def test_network_detail_lanes_players_measures_and_previous_window():
    from app.core import generate_match
    body = TestClient(app).get('/api/graph/roles?minute=67&start=52&team=away').json()['teams']['away']
    events = {e.event_id: e for e in generate_match(SEED)}
    assert sum(e['passes'] for e in body['edges']) == body['completed_passes']
    for lane in body['edges']:
        passes = [events[i] for i in lane['event_ids']]
        assert len(passes) == lane['passes'] and all(52 <= p.minute < 67 for p in passes)
        assert all(p.player_id == lane['from'] and p.recipient_player_id == lane['to'] for p in passes)
        assert lane['progressive'] == sum((p.end_x - p.x) * 1.05 >= 10 for p in passes)
        assert lane['minutes'] == [min(p.minute for p in passes), max(p.minute for p in passes)]
    stats = body['player_stats']
    assert sum(p['made'] for p in stats.values()) == sum(p['received'] for p in stats.values()) == body['completed_passes']
    assert all(p['shirt'] for p in stats.values())
    network = body['network']
    assert network['lanes'] == len(body['edges']) and 0 < network['density'] <= 1
    assert 0 <= network['two_way'] <= 1 and 0 < network['top_three_share'] <= 1 and 0 <= network['progressive_share'] <= 1
    previous = body['previous']
    assert previous['window'] == [37, 52] and previous['edges']
    whole = TestClient(app).get('/api/graph/roles?minute=67&team=away').json()['teams']['away']
    assert 'previous' not in whole  # nothing before the start of the match
