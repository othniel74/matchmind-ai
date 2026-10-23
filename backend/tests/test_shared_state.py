"""More than one replica: shared cache, limits and locks, and one feed consumer relayed to the rest.
Uses an in-memory Redis (fakeredis); without REDIS_URL the app keeps everything per process."""
import asyncio

import pytest

fakeredis = pytest.importorskip('fakeredis')

from app import feed, shared  # noqa: E402
from app.core import generate_match  # noqa: E402
from app.feed import FeedHub  # noqa: E402
from app.guard import ModelCallGuard  # noqa: E402


@pytest.fixture
def redis_server():
    server = fakeredis.FakeServer()
    shared.use(fakeredis.FakeRedis(server=server, decode_responses=True),
               lambda: fakeredis.aioredis.FakeRedis(server=server, decode_responses=True))
    yield server
    shared.use(None, None)


def test_replicas_share_cached_results_and_visitor_limits(redis_server):
    one, two = ModelCallGuard(runs_per_minute=2), ModelCallGuard(runs_per_minute=2)  # two replicas
    one.store(('recap', 'm', 1, 90, 'fan', 'en'), {'narratives': [{'body': 'Merridge won.'}]}, keep=60)
    assert two.cached(('recap', 'm', 1, 90, 'fan', 'en')) == {'narratives': [{'body': 'Merridge won.'}]}
    assert one.allow('1.2.3.4') and two.allow('1.2.3.4')
    assert not one.allow('1.2.3.4') and not two.allow('1.2.3.4')  # the limit holds across replicas
    assert one.allow('5.6.7.8')


def test_kickoff_lock_holds_across_replicas_and_is_released_on_failure(redis_server):
    assert shared.claim('kickoff', 60) is True
    assert shared.claim('kickoff', 60) is False  # another replica cannot start a second feed
    shared.release('kickoff')
    assert shared.claim('kickoff', 60) is True


def test_without_redis_nothing_is_shared():
    assert shared.client() is None and shared.claim('kickoff', 60) is None
    assert shared.status() == {'shared_state': 'memory'}


@pytest.mark.parametrize('source', ['feed', 'vision'])
def test_kickoff_keeps_local_cooldown_when_redis_is_down(monkeypatch, source):
    from fastapi.testclient import TestClient
    from app import main

    class Down:
        def set(self, *args, **kwargs):
            raise ConnectionError('redis down')

    starts = []

    async def start(job):
        starts.append(job)
        return {'job': job}

    monkeypatch.setenv('FEED_JOB_RESOURCE_ID', 'test-feed')
    monkeypatch.setenv('VISION_JOB_RESOURCE_ID', 'test-vision')
    monkeypatch.setattr(main, '_last_kickoff', float('-inf'))
    monkeypatch.setattr(main, '_last_vision', float('-inf'))
    monkeypatch.setattr(feed.FEED, 'status', lambda: {'run': None})
    monkeypatch.setattr(feed, 'start_feed_job', start)
    shared.use(Down(), None)
    try:
        client = TestClient(main.app)
        assert client.post('/api/feed/kickoff', params={'source': source}).status_code == 200
        assert client.post('/api/feed/kickoff', params={'source': source}).status_code == 409
        assert len(starts) == 1
    finally:
        shared.use(None, None)


def test_an_unreachable_redis_falls_back_to_memory(monkeypatch):
    class Down:
        def __getattr__(self, name):
            def fail(*a, **k):
                raise ConnectionError('redis down')
            return fail
    shared.use(Down(), None)
    try:
        guard = ModelCallGuard()
        guard.store(('k',), {'v': 1})
        assert guard.cached(('k',)) == {'v': 1} and guard.allow('9.9.9.9')
        assert shared.claim('kickoff', 60) is None and shared.status()['shared_state'] == 'redis_unreachable'
    finally:
        shared.use(None, None)


def test_the_leader_relays_a_live_match_to_a_follower(redis_server, monkeypatch):
    async def idle():  # no Event Hubs in tests: the leader's hub is driven directly
        await asyncio.Event().wait()
    monkeypatch.setattr(feed, 'consume', idle)
    events = [e for e in generate_match() if e.minute < 12]
    leader_hub, follower_hub = FeedHub(), FeedHub()

    async def scenario():
        r_leader, r_follower = shared.async_client(), shared.async_client()
        await r_leader.set(feed.LEADER_KEY, shared.REPLICA, ex=feed.LEASE_SECONDS)
        lead = asyncio.create_task(feed.lead(r_leader, leader_hub))
        follow = asyncio.create_task(feed.follow(r_follower, follower_hub))
        await asyncio.sleep(0.2)
        viewer: asyncio.Queue = asyncio.Queue(maxsize=5000)
        follower_hub.subscribers.add(viewer)
        leader_hub.handle({'type': 'kickoff', 'feed_run': 'r1', 'match_id': 'synthetic:20261020', 'seed': 20261020})
        for e in events:
            leader_hub.handle({'type': 'event', 'feed_run': 'r1', 'event': e.json()})
        for _ in range(60):
            await asyncio.sleep(0.1)
            if follower_hub.status()['counts']['accepted'] == len(events):
                break
        received = []
        while not viewer.empty():
            received.append(viewer.get_nowait())
        status = follower_hub.status()
        lead.cancel(); follow.cancel()
        await asyncio.gather(lead, follow, return_exceptions=True)
        return received, status

    received, status = asyncio.run(scenario())
    assert status['replica_role'] == 'follower' and status['counts']['accepted'] == len(events)
    assert status['run']['feed_run'] == 'r1'
    assert received[0]['type'] == 'kickoff' and len(received) == len(leader_hub.recent)
    assert [m.get('type') for m in received] == [m.get('type') for m in leader_hub.recent]
    assert list(follower_hub.recent) == list(leader_hub.recent)


def test_a_follower_stands_down_to_take_over_when_the_lease_lapses(redis_server):
    async def scenario():
        r = shared.async_client()
        hub = FeedHub()
        await r.set(feed.LEADER_KEY, 'another-replica', ex=feed.LEASE_SECONDS)
        task = asyncio.create_task(feed.follow(r, hub))
        await asyncio.sleep(0.3)
        assert not task.done() and hub.role == 'follower'
        await r.delete(feed.LEADER_KEY)  # the leader stopped renewing
        await asyncio.wait_for(task, timeout=feed.LEASE_SECONDS)  # follow() returns, to try for the lease
        return True
    assert asyncio.run(scenario())
