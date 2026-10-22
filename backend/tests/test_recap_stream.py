"""The live agent run: steps stream as they complete, then the result; recaps are kept per match state."""
import json

from fastapi.testclient import TestClient

from app.guard import ModelCallGuard
from app.main import app


def parse(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.split('\n\n'):
        lines = dict(line.split(': ', 1) for line in block.split('\n') if line and not line.startswith(':'))
        if 'event' in lines:
            out.append((lines['event'], json.loads(lines['data'])))
    return out


def test_stream_sends_steps_then_the_result():
    with TestClient(app) as client:
        body = client.get('/api/recap/agent/stream', params={'minute': 90, 'language': 'en'}).text
    events = parse(body)
    kinds = [k for k, _ in events]
    assert kinds[-1] == 'done' and kinds[:-1] and set(kinds[:-1]) == {'step'}
    steps = [d['agent'] for k, d in events if k == 'step']
    done = events[-1][1]
    assert steps[0] == 'evidence_gate' and [s['agent'] for s in done['trace']['steps']][:1] == ['evidence_gate']
    assert done['narratives'][0]['kind'] == 'recap'


def test_recaps_can_be_kept_longer_than_the_default():
    guard = ModelCallGuard(cache_seconds=0)
    guard.store(('a',), 1)
    guard.store(('b',), 2, keep=60)
    assert guard.cached(('a',)) is None and guard.cached(('b',)) == 2


def test_live_steps_reach_a_waiting_listener():
    # Agent Framework deep-copies the workflow input; a queue with a waiting reader cannot be copied,
    # so the callback must live outside the job (this failed live with a TypeError).
    import asyncio
    from app.agents import FoundryAgentRuntime
    from app.core import generate_match
    from tests.test_agents import scripted_client, statements, text

    final = 'Merridge won.'
    client = scripted_client({'tactical_analyst': [text(final)], 'match_storyteller': [text(final)],
                              'audience_editor': [text(final)],
                              'fact_checker': [statements({'quote': 'Merridge won', 'type': 'result', 'team': 'away',
                                                           'relation': 'won'})]})

    async def main():
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(FoundryAgentRuntime(client).run_recap(generate_match(), 20261020, 90, 'en', 'fan',
                                                                         on_step=queue.put_nowait))
        seen = []
        while not task.done() or not queue.empty():
            try:
                seen.append((await asyncio.wait_for(queue.get(), 1.0))['agent'])  # a reader is waiting meanwhile
            except asyncio.TimeoutError:
                pass
        return task.result(), seen

    result, seen = asyncio.run(main())
    assert result.trace.engine == 'microsoft_agent_framework'
    assert seen[:3] == ['evidence_gate', 'insight_ranker', 'match_researcher'] and seen[-1] == 'publication_gate'
