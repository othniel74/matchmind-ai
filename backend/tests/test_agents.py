import asyncio
import json
import re
import pytest
from app.agents import FoundryAgentRuntime
from app.core import generate_match, detect_insights
from app.languages import SUPPORTED

MINUTE = 67
PIPELINE = ['evidence_gate', 'insight_ranker', 'tactical_analyst', 'match_storyteller',
            'audience_editor', 'fact_checker', 'publication_gate']
ROLES = (('tactical_analyst', 'football analyst'), ('match_storyteller', 'match storyteller'),
         ('audience_editor', 'adapt text'), ('fact_checker', 'fact extractor'))


def fixture():
    events = [e for e in generate_match() if e.minute < MINUTE]
    insights = detect_insights(events, MINUTE)
    assert insights
    return events, insights


def scripted_client(script):
    """A real Agent Framework chat client whose replies come from `script[role]` (a list or callable)."""
    framework = pytest.importorskip('agent_framework')

    class ScriptedChatClient(framework.BaseChatClient):
        def __init__(self):
            super().__init__()
            self.calls = []

        def as_agent(self, **kwargs):
            # Mirror the Foundry naming rule that rejected underscores in the first live run.
            assert re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', kwargs['name']), kwargs['name']
            return super().as_agent(**kwargs)

        async def _inner_get_response(self, *, messages, stream, options, **kwargs):
            system = options.get('instructions') or ''
            role = next(r for r, marker in ROLES if marker in system)
            prompt = messages[-1].text
            self.calls.append((role, prompt))
            reply = script[role]
            # A one-item script answers every attempt the same way, including retries.
            reply = await reply(prompt) if callable(reply) else (reply.pop(0) if len(reply) > 1 else reply[0])
            return framework.ChatResponse(messages=[framework.Message('assistant', [reply])])

    return ScriptedChatClient()


def text(value):
    return json.dumps({'text': value})


def statements(*items):
    # Every extraction answers the checklist; default each answer to false unless a test sets it.
    from app.agent_workflow import CHECKLIST
    return json.dumps({'statements': [{**{flag: False for flag in CHECKLIST}, **item} for item in items]})


async def honest_extraction(prompt):
    """Extract the whole final text as one supported activity statement."""
    final = prompt.split('text=', 1)[1]
    return statements({'quote': final, 'type': 'activity_change', 'team': 'away', 'relation': 'increase'})


FINAL = 'The away side keeps turning up in the final third.'


def honest():
    return {'tactical_analyst': [text('The away side is appearing more often in advanced areas.')],
            'match_storyteller': [text('The away side keeps arriving in the attacking third.')],
            'audience_editor': [text(FINAL)],
            'fact_checker': honest_extraction}


def run(client, audience='fan', language='en'):
    events, insights = fixture()
    return asyncio.run(FoundryAgentRuntime(client).run(events, insights, audience, language)), insights


def step(result, agent):
    return [s for s in result.trace.steps if s['agent'] == agent]


def test_fallback_without_configuration():
    events, insights = fixture()
    result = asyncio.run(FoundryAgentRuntime().run(events, insights, 'fan', 'en'))
    assert result.trace.engine == 'deterministic_fallback'
    assert result.trace.live is False
    assert result.narratives and all(n['status'] == 'approved' for n in result.narratives)


def test_workflow_runs_real_handoffs_and_keeps_facts_deterministic():
    client = scripted_client(honest())
    result, insights = run(client)
    trace = result.trace
    assert trace.engine == 'microsoft_agent_framework'
    assert trace.handoffs == PIPELINE
    assert [c[0] for c in client.calls] == PIPELINE[2:6]
    first = max(insights, key=lambda i: (i['current_count'] - i['previous_count'], i['minute']))
    assert str(first['current_count']) in client.calls[0][1]
    assert 'audience=fan' in client.calls[2][1] and 'English (language code en)' in client.calls[2][1]
    from app.agent_workflow import checker_prompt
    assert client.calls[3][1] == checker_prompt(FINAL) and 'away=Merridge' in client.calls[3][1]
    published = next(n for n in result.narratives if n['insight_id'] == first['id'])
    assert published['body'] == FINAL and published['engine'] == 'microsoft_agent_framework'
    assert published['evidence_event_ids'] == first['evidence_event_ids']
    assert step(result, 'fact_checker')[0]['status'] == 'verified'
    assert trace.provider == 'ScriptedChatClient' and trace.live is False


def test_fabricated_number_is_blocked_and_later_agents_never_run():
    script = honest()
    script['match_storyteller'] = [text('The away side scored 3 times in ten minutes.')]
    client = scripted_client(script)
    result, _ = run(client)
    assert result.trace.engine == 'deterministic_fallback'
    assert result.trace.fallback_reason == 'match_storyteller:unsupported_number'
    assert result.trace.handoffs == PIPELINE[:4] + ['deterministic_fallback']
    assert {c[0] for c in client.calls} == {'tactical_analyst', 'match_storyteller'}
    assert all(n['engine'] == 'deterministic_fallback' for n in result.narratives)


@pytest.mark.parametrize('claim', ['The away press caused this spell.', 'A clear tactical shift by the away side.',
                                   'La presión visitante domina el partido.'])
def test_causes_and_interpretations_are_blocked_by_the_fast_filter(claim):
    script = honest()
    script['tactical_analyst'] = [text(claim)]
    result, _ = run(scripted_client(script))
    assert result.trace.fallback_reason == 'tactical_analyst:unsupported_claim'


@pytest.mark.parametrize('claim', [
    'In the final minutes the away side kept arriving in the box.',
    'Late in the second half the away side kept coming forward.',
    'En los minutos finales de la segunda mitad, el visitante atacó más.',
    'Antes del descanso el equipo visitante llegó más.'])
def test_match_phase_wording_is_blocked(claim):
    script = honest()
    script['tactical_analyst'] = [text(claim)]
    result, _ = run(scripted_client(script))
    assert result.trace.fallback_reason == 'tactical_analyst:unsupported_timing'


def test_malformed_output_is_retried_once():
    script = honest()
    script['tactical_analyst'] = ['Not JSON at all', script['tactical_analyst'][0]]
    result, _ = run(scripted_client(script))
    analyst = step(result, 'tactical_analyst')[0]
    assert analyst['status'] == 'completed' and analyst['attempts'] == 2
    assert result.trace.engine == 'microsoft_agent_framework'


def test_rule_violation_gets_one_corrective_retry():
    script = honest()
    script['tactical_analyst'] = [text('The away press caused this.'), script['tactical_analyst'][0]]
    client = scripted_client(script)
    result, _ = run(client)
    assert step(result, 'tactical_analyst')[0]['attempts'] == 2
    retry = [prompt for role, prompt in client.calls if role == 'tactical_analyst'][1]
    assert 'rejected (unsupported claim)' in retry and 'press caused' in retry
    assert result.trace.engine == 'microsoft_agent_framework'


def test_slow_agent_times_out_and_falls_back(monkeypatch):
    import app.agent_workflow as workflow
    monkeypatch.setattr(workflow, 'AGENT_TIMEOUT_SECONDS', 0.05)
    async def slow(prompt):
        await asyncio.sleep(1)
        return text('The away side is appearing more often in advanced areas.')
    script = honest()
    script['tactical_analyst'] = slow
    result, _ = run(scripted_client(script))
    assert step(result, 'tactical_analyst')[0]['status'] == 'blocked'
    assert result.trace.fallback_reason == 'tactical_analyst:timeout'


# Semantic fact checking: the model extracts, plain code verifies against claims.

def test_true_comparison_is_verified_against_claims_and_linked():
    claim = 'The away side has had more of the ball and keeps arriving in the attacking third.'
    script = honest()
    script['audience_editor'] = [text(claim)]
    script['fact_checker'] = [statements(
        {'quote': 'The away side has had more of the ball', 'type': 'comparison', 'team': 'away',
         'relation': 'more', 'metric': 'possession'},
        {'quote': 'keeps arriving in the attacking third', 'type': 'activity_change', 'team': 'away',
         'relation': 'increase'})]
    result, insights = run(scripted_client(script))
    assert result.trace.engine == 'microsoft_agent_framework'
    published = next(n for n in result.narratives if n['engine'] == 'microsoft_agent_framework')
    assert published['claim_ids'] == [f'claim:compare:possession:both:{MINUTE}']


def test_false_comparison_triggers_one_revision_then_publishes():
    false = 'The home side had more shots, while the away side keeps arriving in the final third.'
    script = honest()
    script['audience_editor'] = [text(false), text(FINAL)]
    extractions = [statements({'quote': 'The home side had more shots', 'type': 'comparison', 'team': 'home',
                               'relation': 'more', 'metric': 'shots'},
                              {'quote': 'the away side keeps arriving in the final third', 'type': 'activity_change',
                               'team': 'away', 'relation': 'increase'})]
    async def checker(prompt):
        return extractions.pop(0) if extractions else await honest_extraction(prompt)
    script['fact_checker'] = checker
    client = scripted_client(script)
    result, _ = run(client)
    assert [s['status'] for s in step(result, 'fact_checker')] == ['revision_requested', 'verified']
    revision = [p for r, p in client.calls if r == 'audience_editor'][1]
    assert 'not supported by the verified data' in revision and 'more shots' in revision
    assert result.trace.engine == 'microsoft_agent_framework'
    assert result.trace.handoffs == PIPELINE[:6] + ['audience_editor', 'fact_checker', 'publication_gate']


def test_repeated_false_statement_falls_back():
    script = honest()
    script['fact_checker'] = [statements({'quote': FINAL, 'type': 'activity_change', 'team': 'home',
                                          'relation': 'increase'})]
    result, _ = run(scripted_client(script))
    assert result.trace.engine == 'deterministic_fallback'
    assert result.trace.fallback_reason == 'fact_checker:contradicts_evidence'
    assert [s['status'] for s in step(result, 'fact_checker')] == ['revision_requested', 'blocked']


@pytest.mark.parametrize('language,final', [
    ('fr', "L'équipe visiteuse a pris le contrôle en fin de match."),
    ('de', 'Das Gastteam drückt jetzt, weil der Trainer umgestellt hat.'),
    ('ar', 'الفريق الضيف يسيطر على المباراة بالكامل.')])
def test_unsupported_statements_are_caught_in_any_language(language, final):
    script = honest()
    script['audience_editor'] = [text(final)]
    script['fact_checker'] = [statements({'quote': final, 'type': 'other', 'team': 'away', 'relation': 'increase'})]
    result, _ = run(scripted_client(script), language=language)
    assert result.trace.fallback_reason == 'fact_checker:unsupported_statement'
    assert all(n['language'] == language and n['engine'] == 'deterministic_fallback' for n in result.narratives)


@pytest.mark.parametrize('extraction,reason', [
    (statements(), 'no_factual_statement'),
    (statements({'quote': 'something the text never said', 'type': 'activity_change', 'team': 'away',
                 'relation': 'increase'}), 'extraction_mismatch'),
    (statements({'quote': 'away side', 'type': 'activity_change', 'team': 'away', 'relation': 'increase'}),
     'incomplete_extraction'),
    ('not json', 'invalid_output')])
def test_unreliable_extraction_fails_closed(extraction, reason):
    script = honest()
    script['fact_checker'] = [extraction]
    result, _ = run(scripted_client(script))
    assert result.trace.engine == 'deterministic_fallback'
    assert result.trace.fallback_reason == f'fact_checker:{reason}'


@pytest.mark.parametrize('language', SUPPORTED)
def test_every_supported_language_runs_through_the_workflow(language):
    client = scripted_client(honest())
    result, _ = run(client, language=language)
    assert result.trace.engine == 'microsoft_agent_framework'
    assert f'(language code {language})' in [p for r, p in client.calls if r == 'audience_editor'][0]
    assert all(n['language'] == language for n in result.narratives)


def test_arabic_indic_digits_are_blocked():
    script = honest()
    script['audience_editor'] = [text('الفريق الضيف سجل ٣ أهداف')]
    result, _ = run(scripted_client(script), language='ar')
    assert result.trace.fallback_reason == 'audience_editor:unsupported_number'


def test_analyst_prompt_withholds_the_match_minute():
    client = scripted_client(honest())
    run(client)
    prompt = client.calls[0][1]
    assert f'minute {MINUTE}' not in prompt and str(MINUTE) not in prompt


def test_live_required_mode_rejects_fallback():
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get(f'/api/agents/run?minute={MINUTE}&require_live=true').status_code == 503
    assert TestClient(app).get(f'/api/agents/run?minute={MINUTE}&language=xx').status_code == 422


def test_optional_sdk_constructs_foundry_client_without_cloud_calls(monkeypatch):
    import importlib.util
    if importlib.util.find_spec('agent_framework_foundry') is None:
        pytest.skip('Optional Microsoft SDK is not installed')
    monkeypatch.setenv('AZURE_AI_PROJECT_ENDPOINT', 'https://example.services.ai.azure.com/api/projects/test')
    monkeypatch.setenv('AZURE_AI_MODEL_DEPLOYMENT_NAME', 'test-deployment')
    async def construct():
        runtime = FoundryAgentRuntime()
        try:
            client = runtime._client()
            assert type(client).__name__ == 'FoundryChatClient'
            assert callable(client.as_agent(name='contract-check', instructions='Describe only supplied evidence.').run)
        finally:
            if runtime._credential is not None:
                await runtime._credential.close()
    asyncio.run(construct())


def test_provider_selection(monkeypatch):
    from app.agents import selected_provider
    assert selected_provider() is None
    monkeypatch.setenv('AZURE_AI_PROJECT_ENDPOINT', 'https://example.services.ai.azure.com/api/projects/p')
    monkeypatch.setenv('AZURE_AI_MODEL_DEPLOYMENT_NAME', 'project-model')
    assert selected_provider() == 'foundry'
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://example.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT', 'chat')
    assert selected_provider() == 'azure_openai'
    monkeypatch.setenv('MATCHMIND_AI_PROVIDER', 'foundry')
    assert selected_provider() == 'foundry'
    monkeypatch.setenv('MATCHMIND_AI_PROVIDER', 'other')
    with pytest.raises(RuntimeError):
        selected_provider()


def test_azure_openai_key_client_constructs_without_calls_and_status_hides_secrets(monkeypatch):
    pytest.importorskip('agent_framework.openai')
    from fastapi.testclient import TestClient
    from app.main import app
    secret = 'test-secret-value-not-real'
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://example.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT', 'chat')
    monkeypatch.setenv('AZURE_OPENAI_API_KEY', secret)
    async def construct():
        runtime = FoundryAgentRuntime()
        client = runtime._client()
        assert type(client).__name__ == 'OpenAIChatCompletionClient' and runtime._credential is None
        assert callable(client.as_agent(name='contract-check', instructions='Describe only supplied evidence.').run)
    asyncio.run(construct())
    response = TestClient(app).get('/api/runtime')
    body = response.json()
    assert body['provider'] == 'azure_openai' and body['auth'] == 'api_key' and body['configured']
    assert secret not in response.text and 'example.openai.azure.com' not in response.text


# Tone: emphatic wording must match the size of the change.

def _single_statement(**fields):
    script = honest()
    script['audience_editor'] = [text(fields.pop('final', FINAL))]
    script['fact_checker'] = [statements({'quote': fields.pop('quote', FINAL), **fields})]
    return run(scripted_client(script))[0]


def test_extreme_wording_is_overstated_even_when_true():
    result = _single_statement(type='activity_change', team='away', relation='increase', intensity='extreme')
    assert result.trace.fallback_reason == 'fact_checker:overstated'


def test_strong_wording_is_allowed_for_a_large_change():
    events, insights = fixture()
    insight = max(insights, key=lambda i: i['current_count'] - i['previous_count'])
    assert insight['current_count'] >= 1.75 * insight['previous_count']
    result = _single_statement(type='activity_change', team='away', relation='increase', intensity='strong')
    assert result.trace.engine == 'microsoft_agent_framework'


def test_strong_wording_on_a_narrow_comparison_is_overstated():
    from app.claims import measure
    events, _ = fixture()
    home, away = (measure(events, 'shots', t, MINUTE)[0] for t in ('home', 'away'))
    assert max(home, away) < 1.5 * min(home, away)
    leader = 'home' if home > away else 'away'
    final = 'They have had far more shots and keep arriving in the final third.'
    script = honest()
    script['audience_editor'] = [text(final)]
    script['fact_checker'] = [statements(
        {'quote': 'They have had far more shots', 'type': 'comparison', 'team': leader, 'relation': 'more',
         'metric': 'shots', 'intensity': 'strong'},
        {'quote': 'keep arriving in the final third', 'type': 'activity_change', 'team': 'away',
         'relation': 'increase'})]
    result, _ = run(scripted_client(script))
    assert result.trace.fallback_reason == 'fact_checker:overstated'


# Rate limits: wait as instructed, then fall back cleanly if they persist.

class _RateLimited(Exception):
    status_code = 429

    class response:
        headers = {'retry-after': '0.5'}


def test_rate_limit_waits_and_retries(monkeypatch):
    import app.agent_workflow as workflow
    sleeps = []
    real_sleep = asyncio.sleep
    async def fake_sleep(seconds):
        sleeps.append(seconds)
        await real_sleep(0)
    monkeypatch.setattr(workflow.asyncio, 'sleep', fake_sleep)
    calls = []
    async def limited_once(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            raise _RateLimited('429 Too Many Requests')
        return text('The away side is appearing more often in advanced areas.')
    script = honest()
    script['tactical_analyst'] = limited_once
    result, _ = run(scripted_client(script))
    assert result.trace.engine == 'microsoft_agent_framework'
    assert sleeps == [0.5] and step(result, 'tactical_analyst')[0]['rate_limit_waits'] == 1


def test_persistent_rate_limit_falls_back(monkeypatch):
    import app.agent_workflow as workflow
    real_sleep = asyncio.sleep
    async def fake_sleep(seconds):
        await real_sleep(0)
    monkeypatch.setattr(workflow.asyncio, 'sleep', fake_sleep)
    async def always_limited(prompt):
        raise _RateLimited('429 Too Many Requests')
    script = honest()
    script['tactical_analyst'] = always_limited
    result, _ = run(scripted_client(script))
    assert result.trace.fallback_reason == 'tactical_analyst:rate_limited'
    assert step(result, 'tactical_analyst')[0]['rate_limit_waits'] == workflow.RATE_LIMIT_RETRIES


@pytest.mark.parametrize('flag', ['mentions_match_time', 'gives_cause', 'mentions_chances_or_threat',
                                  'is_prediction', 'judges_performance', 'claims_dominance'])
def test_any_checklist_flag_blocks_even_a_true_activity_statement(flag):
    result = _single_statement(type='activity_change', team='away', relation='increase', **{flag: True})
    assert result.trace.fallback_reason == f'fact_checker:unsupported_{flag}'


def test_extraction_without_the_checklist_is_rejected():
    script = honest()
    script['fact_checker'] = [json.dumps({'statements': [{'quote': FINAL, 'type': 'activity_change',
                                                          'team': 'away', 'relation': 'increase'}]})]
    result, _ = run(scripted_client(script))
    assert result.trace.fallback_reason == 'fact_checker:invalid_output'


# Recaps: results and scorers are verified against events by code.

def run_recap(client, minute=90, language='en'):
    events = generate_match()
    return asyncio.run(FoundryAgentRuntime(client).run_recap(events, 20261020, minute, language))


def recap_script(final, extraction):
    return {'tactical_analyst': [text('Merridge beat Calderbrook.')], 'match_storyteller': [text('Merridge beat Calderbrook.')],
            'audience_editor': [text(final)], 'fact_checker': [statements(*extraction)]}


def test_recap_publishes_verified_result_and_scorer():
    final = 'Merridge beat Calderbrook, with Pedro Valença scoring twice.'
    client = scripted_client(recap_script(final, [
        {'quote': 'Merridge beat Calderbrook', 'type': 'result', 'team': 'away', 'relation': 'won'},
        {'quote': 'with Pedro Valença scoring twice', 'type': 'scorer', 'team': 'away', 'player': 'Pedro Valença',
         'intensity': 'strong'}]))
    result = run_recap(client)
    assert result.trace.engine == 'microsoft_agent_framework'
    recap = result.narratives[0]
    assert recap['kind'] == 'recap' and recap['body'] == final
    assert recap['claim_ids'] == ['claim:score:goals:both:90']
    assert recap['recap']['engine'] == 'deterministic_verified'  # the verified recap always travels with it
    analyst_prompt = client.calls[0][1]
    assert 'Merridge won' in analyst_prompt and 'Pedro Valença (Merridge, goals=2)' in analyst_prompt


@pytest.mark.parametrize('statement,reason', [
    ({'quote': 'Calderbrook beat Merridge', 'type': 'result', 'team': 'home', 'relation': 'won'}, 'contradicts_result'),
    ({'quote': 'Callum Rhodes scored for Calderbrook', 'type': 'scorer', 'team': 'home', 'player': 'Callum Rhodes'},
     'contradicts_scorers'),
    ({'quote': 'Merridge are winning', 'type': 'result', 'team': 'away', 'relation': 'won'}, 'contradicts_result'),
])
def test_recap_blocks_false_results_and_scorers(statement, reason):
    minute = 60 if statement['quote'] == 'Merridge are winning' else 90
    result = run_recap(scripted_client(recap_script(statement['quote'] + '.', [statement])), minute=minute)
    assert result.trace.engine == 'deterministic_fallback'
    assert result.trace.fallback_reason == f'fact_checker:{reason}'
    assert result.narratives[0]['body'].startswith(('Full-time', 'Match so far'))


def test_recap_without_a_model_returns_the_verified_recap():
    events = generate_match()
    result = asyncio.run(FoundryAgentRuntime().run_recap(events, 20261020, 45, 'fr'))
    assert result.trace.engine == 'deterministic_fallback'
    assert result.narratives[0]['body'].startswith('Mi-temps')


def test_list_sentences_can_be_split_into_one_claim_per_statistic():
    final = 'Merridge won, leading in shots, expected goals and corners.'
    extraction = [{'quote': 'Merridge won', 'type': 'result', 'team': 'away', 'relation': 'won'}] + [
        {'quote': f'Merridge leading in {words}', 'type': 'comparison', 'team': 'away', 'relation': 'more', 'metric': m}
        for words, m in (('shots', 'shots'), ('expected goals', 'xg'), ('corners', 'corners'))]
    result = run_recap(scripted_client(recap_script(final, extraction)))
    assert result.trace.engine == 'microsoft_agent_framework'
    assert len(result.narratives[0]['claim_ids']) == 4


def test_recap_writers_get_recap_rules():
    client = scripted_client(recap_script('Merridge won.', [
        {'quote': 'Merridge won', 'type': 'result', 'team': 'away', 'relation': 'won'}]))
    seen = []
    original = client.as_agent
    def capture(**kwargs):
        seen.append(kwargs['instructions'])
        return original(**kwargs)
    client.as_agent = capture
    run_recap(client)
    writers = [i for i in seen if 'football analyst' in i or 'storyteller' in i or 'adapt text' in i]
    assert len(writers) == 3 and all('the scorers (names exactly as supplied)' in i for i in writers)
    assert not any('never mention possession' in i for i in writers)


def test_request_scoped_clients_and_credentials_are_closed():
    closed = []

    class Closable:
        def __init__(self, label):
            self.label = label

        async def close(self):
            closed.append(self.label)

    class FakeFoundryClient:  # like FoundryChatClient: no close() of its own
        def __init__(self):
            self.client, self.project_client = Closable('openai'), Closable('project')

    runtime = FoundryAgentRuntime()
    def fake_client():
        runtime.client, runtime._credential = FakeFoundryClient(), Closable('credential')
        raise RuntimeError('model unavailable')
    runtime._client = fake_client
    events, insights = fixture()
    result = asyncio.run(runtime.run(events, insights, 'fan', 'en'))
    assert result.trace.engine == 'deterministic_fallback'
    assert sorted(closed) == ['credential', 'openai', 'project'] and runtime.client is None


def test_arabic_attached_prefixes_and_transliterated_scorers_are_grounded():
    final = 'فاز مريدج، وسجل بيدرو فالينسا والركنيات لمريدج.'
    extraction = [
        {'quote': 'فاز مريدج', 'type': 'result', 'team': 'away', 'relation': 'won'},
        {'quote': 'سجل بيدرو فالينسا', 'type': 'scorer', 'team': 'away', 'player': 'Pedro Valença'},
        {'quote': 'الركنيات لمريدج', 'type': 'comparison', 'team': 'away', 'relation': 'more', 'metric': 'corners'}]
    result = run_recap(scripted_client(recap_script(final, extraction)), language='ar')
    assert result.trace.engine == 'microsoft_agent_framework', result.trace.fallback_reason


def test_saying_the_match_ended_before_full_time_is_rejected():
    statement = {'quote': 'The match ended with Merridge ahead', 'type': 'result', 'team': 'away', 'relation': 'won'}
    result = run_recap(scripted_client(recap_script(statement['quote'] + '.', [statement])), minute=60)
    assert result.trace.fallback_reason == 'fact_checker:contradicts_result'


def test_checker_prompt_carries_the_roster():
    from app.agent_workflow import checker_prompt
    prompt = checker_prompt('text')
    assert 'roster: ' in prompt and 'Pedro Valença (Merridge)' in prompt and 'Callum Rhodes (Calderbrook)' in prompt


@pytest.mark.parametrize('quote', ['They have had far more shots', 'Ha tenido muchísima más posesión',
                                   'Hanno decisamente più tiri', 'لديهم تسديدات أكثر بكثير'])
def test_intensifier_backstop_overrides_a_neutral_label(quote):
    script = honest()
    final = f'{quote}, and keep arriving in the final third.'
    script['audience_editor'] = [text(final)]
    script['fact_checker'] = [statements(
        {'quote': quote, 'type': 'comparison', 'team': 'away', 'relation': 'more', 'metric': 'shots',
         'intensity': 'neutral'},
        {'quote': 'keep arriving in the final third', 'type': 'activity_change', 'team': 'away', 'relation': 'increase'})]
    result, _ = run(scripted_client(script))
    assert result.trace.fallback_reason == 'fact_checker:overstated'


def test_so_far_is_not_emphasis():
    final = 'Merridge have had more shots so far, and keep arriving in the final third.'
    script = honest()
    script['audience_editor'] = [text(final)]
    script['fact_checker'] = [statements(
        {'quote': 'Merridge have had more shots so far', 'type': 'comparison', 'team': 'away', 'relation': 'more',
         'metric': 'shots'},
        {'quote': 'keep arriving in the final third', 'type': 'activity_change', 'team': 'away', 'relation': 'increase'})]
    result, _ = run(scripted_client(script))
    assert result.trace.engine == 'microsoft_agent_framework'
