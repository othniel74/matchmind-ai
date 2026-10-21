"""Pitchlight's MCP server: protocol, tool contract and answers, over the API's /mcp endpoint."""
import json

import pytest
from fastapi.testclient import TestClient

from app.ask import validate_intent
from app.main import app

HEADERS = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:  # the lifespan starts the MCP session manager
        yield c


def rpc(client, method, params=None, id_=1):
    r = client.post('/mcp', headers=HEADERS, json={'jsonrpc': '2.0', 'id': id_, 'method': method, 'params': params or {}})
    assert r.status_code == 200, r.text
    return r.json()


def call(client, name, arguments):
    result = rpc(client, 'tools/call', {'name': name, 'arguments': arguments})['result']
    return result, result.get('structuredContent')


def test_initialize_announces_tools(client):
    result = rpc(client, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                        'clientInfo': {'name': 'test', 'version': '1'}})['result']
    assert result['serverInfo']['name'] == 'pitchlight' and 'tools' in result['capabilities']
    assert 'synthetic' in result['instructions'].lower() or 'fictional' in result['instructions'].lower()


def test_every_tool_is_read_only_and_documented(client):
    tools = rpc(client, 'tools/list')['result']['tools']
    names = {t['name'] for t in tools}
    assert {'match_state', 'key_moments', 'why_moment', 'network_roles', 'xg_chain', 'goal_buildups',
            'story_so_far', 'correction_impact', 'match_recap', 'answer_question', 'list_claims',
            'validate_claim', 'squads'} <= names
    for tool in tools:
        assert tool['annotations']['readOnlyHint'] is True and tool['annotations']['destructiveHint'] is False
        assert tool['description'] and tool['inputSchema']['type'] == 'object'
    intents = next(t for t in tools if t['name'] == 'answer_question')['inputSchema']['properties']['intent']
    assert 'unsupported' in json.dumps(intents)


def test_tools_return_time_scoped_evidence(client):
    _, state = call(client, 'match_state', {'minute': 60})
    assert state['score'] == {'home': 1, 'away': 2} and state['context']['minute'] == 60
    _, moments = call(client, 'key_moments', {'minute': 60, 'language': 'ar', 'kinds': ['goal']})
    assert moments['moments'] and all(m['minute'] <= 60 and m['direction'] == 'rtl' for m in moments['moments'])
    _, why = call(client, 'why_moment', {'moment_id': moments['moments'][-1]['id'], 'minute': 60})
    assert why['evidence_event_ids'] and why['buildup']
    _, roles = call(client, 'network_roles', {'team': 'away', 'minute': 60, 'window_minutes': 15})
    assert roles['window'] == [45, 60] and roles['connector']
    _, impact = call(client, 'correction_impact', {'event_id': why['evidence_event_ids'][-1]})
    assert why['moment_id'] in impact['moments']


def test_answers_use_structured_intent_and_refuse_off_topic(client):
    _, typed = call(client, 'answer_question', {'question': 'How many corners for Calderbrook?', 'minute': 60,
                                                'language': 'fr', 'intent': 'stat', 'metric': 'corners'})
    assert typed['intent'] == 'stat' and 'corners' in typed['answer'] and typed['claim_ids']
    _, refused = call(client, 'answer_question', {'question': 'Who wins the league?', 'intent': 'unsupported'})
    assert refused['supported'] is False and refused['evidence_event_ids'] == []


def test_invalid_arguments_are_tool_errors_not_crashes(client):
    result, _ = call(client, 'match_state', {'minute': 120})
    assert result['isError'] and 'between 1 and 90' in result['content'][0]['text']
    result, _ = call(client, 'why_moment', {'moment_id': 'nope'})
    assert result['isError'] and 'key_moments' in result['content'][0]['text']


def test_model_intent_is_validated():
    assert validate_intent({'intent': 'player', 'player': 'Valenca'}, 'q')['player_id'] == 'away-03'
    assert validate_intent({'intent': 'stat', 'metric': 'made_up', 'team': 'both'}, 'q') == \
        {'intent': 'stat', 'team': None, 'player_id': None, 'metric': None}
    assert validate_intent({'intent': 'invent'}, 'who scored')['intent'] == 'scorers'


def test_rejects_unknown_host(client):
    r = client.post('/mcp', headers={**HEADERS, 'Host': 'evil.example'},
                    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
    assert r.status_code in (400, 421)
