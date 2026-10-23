"""Event Hubs match feed: the consumer's handling of kick-off, events, duplicates, bad events and
full time, the API surface, and the producer's message format. No Azure connection needed."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.core import generate_match
from app.feed import FeedHub
from app.main import app

RUN = 'run-1'


def kickoff(run=RUN):
    return {'type': 'kickoff', 'feed_run': run, 'match_id': 'synthetic:20261020', 'seed': 20261020, 'speed': 30}


def event(e, run=RUN):
    return {'type': 'event', 'feed_run': run, 'match_id': 'synthetic:20261020', 'event': e.json()}


@pytest.fixture(scope='module')
def events():
    return generate_match()


def test_a_full_feed_matches_batch_analysis(events):
    from app.experience import Profile
    from app.live import LiveMatch
    hub = FeedHub()
    hub.handle(kickoff())
    for e in events:
        hub.handle(event(e))
    hub.handle({'type': 'full_time', 'feed_run': RUN})
    assert hub.counts['accepted'] == len(events) and hub.counts['rejected'] == 0
    assert hub.run['status'] == 'full_time' and hub.status()['score'] == {'home': 2, 'away': 3}
    batch = LiveMatch(20261020, Profile(audience='broadcast'))
    expected = [m for e in events for m in batch.ingest(e) if m['type'] == 'moment']
    expected += [m for m in batch.finish() if m['type'] == 'moment']
    assert hub.counts['moments'] == len(expected)


def test_duplicates_are_skipped_and_bad_events_rejected(events):
    hub = FeedHub()
    hub.handle(kickoff())
    for e in events[:50]:
        hub.handle(event(e))
    hub.handle(event(events[10]))  # at-least-once redelivery
    bad = replace(events[50], minute=0, second=0, event_id='evt-bad')  # goes back in time
    out = hub.handle(event(bad))
    assert hub.counts == {'accepted': 50, 'rejected': 1, 'duplicates': 1, 'moments': hub.counts['moments']}
    assert out[0]['type'] == 'rejected' and 'evt-bad' in hub.last_error
    hub.handle(event(events[50]))  # the stream continues after a rejected event
    assert hub.counts['accepted'] == 51


def test_messages_from_another_run_or_before_kickoff_are_ignored(events):
    hub = FeedHub()
    assert hub.handle(event(events[0])) == []
    hub.handle(kickoff('run-2'))
    assert hub.handle(event(events[0], run='run-1')) == []
    assert hub.counts['accepted'] == 0


def test_new_kickoff_resets_the_run(events):
    hub = FeedHub()
    hub.handle(kickoff('a'))
    for e in events[:20]:
        hub.handle(event(e, 'a'))
    hub.handle(kickoff('b'))
    assert hub.counts['accepted'] == 0 and hub.run['feed_run'] == 'b' and not hub.recent or \
        hub.recent[0]['type'] == 'kickoff'


def test_subscribers_receive_messages_and_stalled_ones_are_dropped(events):
    import asyncio
    hub = FeedHub()
    fast, stalled = asyncio.Queue(maxsize=1000), asyncio.Queue(maxsize=1)
    hub.subscribers |= {fast, stalled}
    hub.handle(kickoff())
    for e in events[:200]:
        hub.handle(event(e))
    assert fast.qsize() > 1 and stalled not in hub.subscribers


def test_feed_api_without_event_hubs(monkeypatch):
    monkeypatch.delenv('EVENTHUB_NAMESPACE', raising=False)
    monkeypatch.delenv('FEED_JOB_RESOURCE_ID', raising=False)
    with TestClient(app) as client:
        body = client.get('/api/feed').json()
        assert body['enabled'] is False and body['kickoff_available'] is False
        assert client.post('/api/feed/kickoff').status_code == 503
        with client.websocket_connect('/ws/feed') as ws:
            assert ws.receive_json()['type'] == 'status'


def test_producer_message_format(events):
    """The producer sends kick-off, every event in order, then full time, keyed by match."""
    pytest.importorskip("azure.eventhub")
    import asyncio
    import app.feed as feed

    sent = []

    class Batch(list):
        def add(self, data):
            self.append(data)

    class Producer:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def create_batch(self, partition_key):
            assert partition_key == 'synthetic:20261020'
            return Batch()
        async def send_batch(self, batch):
            sent.extend(batch)

    class Cred:
        async def close(self): pass

    import azure.eventhub.aio as aio
    original, original_cred = aio.EventHubProducerClient, feed.credential
    aio.EventHubProducerClient, feed.credential = Producer, Cred
    try:
        result = asyncio.run(feed.publish(speed=3600, namespace='example.servicebus.windows.net'))
    finally:
        aio.EventHubProducerClient, feed.credential = original, original_cred
    import json
    bodies = [json.loads(d.body_as_str()) for d in sent]
    assert bodies[0]['type'] == 'kickoff' and bodies[-1]['type'] == 'full_time'
    assert [b['event']['event_id'] for b in bodies[1:-1]] == [e.event_id for e in events]
    assert result['messages'] == len(events) + 2 and {b['feed_run'] for b in bodies} == {result['feed_run']}


def test_vision_kickoff_runs_once_at_a_time(monkeypatch):
    import app.feed as feed
    import app.main as main
    started = []

    async def fake_start(job=None):
        started.append(job)
        return {'execution': 'exec-1'}

    monkeypatch.setenv('VISION_JOB_RESOURCE_ID', '/subscriptions/x/jobs/matchmind-vision')
    monkeypatch.setattr(feed, 'start_feed_job', fake_start)
    monkeypatch.setattr(main, '_last_vision', float('-inf'))
    with TestClient(app) as client:
        first = client.post('/api/feed/kickoff?source=vision')
        assert first.status_code == 200 and first.json()['source'] == 'vision'  # a fresh server accepts the first run
        assert client.post('/api/feed/kickoff?source=vision').status_code == 409
        assert client.get('/api/feed').json()['vision_available'] is True
    assert started == ['/subscriptions/x/jobs/matchmind-vision']


def test_video_runs_show_only_video_derived_moments(events):
    hub = FeedHub()
    hub.handle({**kickoff('v'), 'source': 'vision'})
    for e in events[:300]:
        hub.handle(event(e, 'v'))
    kinds = {m['moment']['kind'] for m in hub.recent if m.get('type') == 'moment'}
    assert kinds and not kinds & {'top_speed', 'distance'}


def test_the_event_hubs_consumer_callbacks_drive_the_feed(monkeypatch, events):
    """Regression: a refactor left consume()'s callbacks pointing at an undefined name, the SDK
    swallowed the error, and the live feed silently stayed at 'starting' (v28). This drives the
    real callbacks through a stand-in for the Event Hubs client."""
    import asyncio
    import json as _json
    import sys
    import types
    from app import feed as feed_module

    class Partition:
        partition_id = '0'

    class Message:
        def __init__(self, body):
            self.body, self.enqueued_time = _json.dumps(body), None

        def body_as_str(self):
            return self.body

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def receive(self, on_event, starting_position, on_error, on_partition_initialize):
            await on_partition_initialize(Partition())
            await on_event(Partition(), Message(kickoff()))
            for e in events[:30]:
                await on_event(Partition(), Message({'type': 'event', 'feed_run': RUN, 'event': e.json()}))
            raise asyncio.CancelledError  # end the consumer's endless loop

    class FakeCredential:
        async def close(self):
            pass

    sdk = types.ModuleType('azure.eventhub.aio')
    sdk.EventHubConsumerClient = FakeClient
    monkeypatch.setitem(sys.modules, 'azure.eventhub.aio', sdk)
    monkeypatch.setattr(feed_module, 'credential', lambda: FakeCredential())
    monkeypatch.setenv('EVENTHUB_NAMESPACE', 'test.servicebus.windows.net')
    hub = feed_module.FeedHub()
    monkeypatch.setattr(feed_module, 'FEED', hub)  # called exactly as the app calls it: no hub argument
    try:
        asyncio.run(feed_module.consume())
    except asyncio.CancelledError:
        pass
    assert hub.consumer == {'status': 'connected', 'partition': '0'}
    assert hub.run['feed_run'] == RUN and hub.counts['accepted'] == 30 and hub.counts['rejected'] == 0
