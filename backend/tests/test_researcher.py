"""The match researcher: an agent chooses the recap's angle through MCP; code resolves and verifies."""
import asyncio
import json

import pytest

pytest.importorskip('agent_framework')

from app import agent_workflow as wf  # noqa: E402
from app.agent_workflow import ResearchBrief, RoleChoice, recap_prompt, resolve_brief, role_holder, verify_statements  # noqa: E402
from app.agents import FoundryAgentRuntime  # noqa: E402
from app.core import generate_match  # noqa: E402
from app.recap import recap_facts  # noqa: E402
from tests.test_agents import scripted_client, statements, text  # noqa: E402

EVENTS = generate_match()
FLAGS = dict.fromkeys(wf.CHECKLIST, False)


def role_statement(quote, team, relation, player):
    return {'quote': quote, 'type': 'role', 'team': team, 'relation': relation, 'player': player, 'metric': None,
            'intensity': 'neutral', **FLAGS}


def test_code_resolves_the_brief_dedupes_and_limits():
    brief = ResearchBrief(angle='Merridge ran the game through one player.',
                          metrics=['possession', 'possession', 'shots', 'xg', 'corners'],
                          roles=[RoleChoice(team='away', role='hub'), RoleChoice(team='away', role='hub'),
                                 RoleChoice(team='home', role='hub')])
    resolved = resolve_brief(brief, EVENTS, 90)
    assert resolved['metrics'] == ['possession', 'shots', 'xg']
    assert [(r['team'], r['role']) for r in resolved['roles']] == [('away', 'hub'), ('home', 'hub')]
    assert all(r['player'] == role_holder(EVENTS, r['team'], 90, r['role']) for r in resolved['roles'])


def test_brief_narrows_the_writers_facts():
    facts = recap_facts(EVENTS, 90)
    brief = {'metrics': ['possession'], 'roles': [{'team': 'away', 'role': 'hub',
                                                   'player': role_holder(EVENTS, 'away', 90, 'hub')}]}
    prompt = recap_prompt(facts, brief)
    assert 'possession' in prompt and 'corners' not in prompt and 'shots_on_target' not in prompt
    assert f"most involved in Merridge's passing: {brief['roles'][0]['player']}" in prompt
    assert 'corners' in recap_prompt(facts)  # without a brief, every statistic leader as before


def test_role_statements_are_verified_by_code():
    holder = role_holder(EVENTS, 'away', 90, 'key_link')
    right = f'{holder} was the key link for Merridge'
    assert verify_statements([role_statement(right, 'away', 'key_link', holder)], right, None, EVENTS, 90)[0] is None
    other = next(p for p in ('Aiden Mburu', 'Ivo Brankov', 'Pedro Valença') if p != holder)
    wrong = f'{other} was the key link for Merridge'
    failure, _, rejected = verify_statements([role_statement(wrong, 'away', 'key_link', other)], wrong, None, EVENTS, 90)
    assert failure == 'contradicts_roles' and rejected == [wrong]


def recap_run(client, url=None):
    runtime = FoundryAgentRuntime(client)
    original = wf.NarrativeJob

    def job(*args, **kwargs):  # an injected client runs offline unless a test supplies the MCP address
        return original(*args, **{**kwargs, 'mcp_url': url})
    wf.NarrativeJob = job
    try:
        return asyncio.run(runtime.run_recap(EVENTS, 20261020, 90, 'en'))
    finally:
        wf.NarrativeJob = original


def script(final, extraction):
    return {'tactical_analyst': [text(final)], 'match_storyteller': [text(final)], 'audience_editor': [text(final)],
            'fact_checker': [extraction]}


def test_offline_the_researcher_is_skipped_and_says_why():
    client = scripted_client(script('Merridge won.', statements(
        {'quote': 'Merridge won', 'type': 'result', 'team': 'away', 'relation': 'won'})))
    result = recap_run(client)
    research = next(s for s in result.trace.steps if s['agent'] == 'match_researcher')
    assert research['status'] == 'skipped' and research['reason'] == 'no_mcp_server'
    assert result.trace.handoffs[:4] == ['evidence_gate', 'insight_ranker', 'match_researcher', 'tactical_analyst']


def test_researcher_choices_reach_the_writer_and_the_trace(monkeypatch):
    holder = role_holder(EVENTS, 'away', 90, 'hub')

    async def fake_research(client, url, minute):
        assert url == 'http://mcp.test/mcp' and minute == 90
        return (ResearchBrief(angle='Possession and one passer tell this story.', metrics=['possession'],
                              roles=[RoleChoice(team='away', role='hub')]),
                [{'tool': 'network_roles', 'arguments': {'team': 'away', 'minute': 90}},
                 {'tool': 'list_claims', 'arguments': {'minute': 90}}])
    monkeypatch.setattr(wf, 'run_research', fake_research)
    final = f'Merridge won, and {holder} was the most involved in their passing.'
    client = scripted_client(script(final, statements(
        {'quote': 'Merridge won', 'type': 'result', 'team': 'away', 'relation': 'won'},
        {'quote': f'{holder} was the most involved in their passing', 'type': 'role', 'team': 'away',
         'relation': 'hub', 'player': holder})))
    result = recap_run(client, 'http://mcp.test/mcp')
    research = next(s for s in result.trace.steps if s['agent'] == 'match_researcher')
    assert research['status'] == 'completed' and [c['tool'] for c in research['tool_calls']] == ['network_roles', 'list_claims']
    assert research['chose']['roles'][0]['player'] == holder
    analyst_prompt = next(p for role, p in client.calls if role == 'tactical_analyst')
    assert 'Passing roles' in analyst_prompt and holder in analyst_prompt and 'corners' not in analyst_prompt
    assert result.trace.engine == 'microsoft_agent_framework', (result.trace.fallback_reason, result.trace.steps[-2:])
    assert result.narratives[0]['body'] == final


def test_failed_research_never_blocks_the_recap(monkeypatch):
    async def broken(client, url, minute):
        raise ConnectionError('MCP down')
    monkeypatch.setattr(wf, 'run_research', broken)
    client = scripted_client(script('Merridge won.', statements(
        {'quote': 'Merridge won', 'type': 'result', 'team': 'away', 'relation': 'won'})))
    result = recap_run(client, 'http://mcp.test/mcp')
    research = next(s for s in result.trace.steps if s['agent'] == 'match_researcher')
    assert research == {**research, 'status': 'skipped', 'reason': 'ConnectionError'}
    assert result.trace.engine == 'microsoft_agent_framework'


def test_naming_statistics_or_goals_is_not_talking_about_chances():
    from app.agent_workflow import CHECKLIST
    rule = CHECKLIST['mentions_chances_or_threat']
    assert 'expected goals' in rule and 'not a mention of chances' in rule
