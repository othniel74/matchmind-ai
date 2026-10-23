"""Event-driven match feed on Azure Event Hubs.

    producer (Container Apps Job)  ->  Event Hubs `match-events`  ->  consumer (this app)  ->  browsers
    python -m app.feed publish          partition key = match           validate, interpret,     /ws/feed

The producer publishes a synthetic match in order, as a live data provider would: a kick-off
message, every event, then full time. The consumer validates each event against the stream so
far with StreamValidator, detects moments as they happen with LiveMatch, and fans the results
out to WebSocket clients. Duplicated deliveries are recognized and skipped; invalid events are
counted and reported, never applied.

State is held in memory and rebuilt from the log: on start the consumer reads the last
FEED_REPLAY_MINUTES of the hub and resumes from the latest kick-off (event sourcing), so no
separate checkpoint store is needed.

With more than one replica (REDIS_URL, see shared.py) exactly one replica consumes: it holds a
lease in Redis and relays every message and its status there. The others follow, fanning the
relayed messages out to their own viewers, and take over when the lease lapses (about 15 s);
the new leader rebuilds the run from the log as above.

All Azure access uses Entra ID (managed identity in Azure, `az login` locally); no connection
strings. Configure with EVENTHUB_NAMESPACE (for example `matchmind-feed.servicebus.windows.net`)
and EVENTHUB_NAME (default `match-events`).
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from . import shared

log = logging.getLogger('matchmind.feed')
HUB = os.getenv('EVENTHUB_NAME', 'match-events')
SEED = 20261020
PHYSICAL_KINDS = {'top_speed', 'distance'}


def enabled() -> bool:
    return bool(os.getenv('EVENTHUB_NAMESPACE'))


class FeedHub:
    """The current feed run: validation, interpretation, counters and WebSocket fan-out."""

    def __init__(self, backlog: int = 300):
        self.run: dict[str, Any] | None = None
        self.live = None
        self.counts = {'accepted': 0, 'rejected': 0, 'duplicates': 0, 'moments': 0}
        self.last_error: str | None = None
        self.last_enqueued: str | None = None
        self.recent: deque[dict[str, Any]] = deque(maxlen=backlog)
        self.subscribers: set[asyncio.Queue] = set()
        self.consumer: dict[str, Any] = {'status': 'disabled' if not enabled() else 'starting'}
        self.role = 'single'                 # 'leader' or 'follower' when replicas share state
        self.relay: asyncio.Queue | None = None

    def local_status(self) -> dict[str, Any]:
        state = self.live.state() if self.live is not None else None
        return {'enabled': enabled(), 'consumer': self.consumer, 'hub': HUB, 'run': self.run,
                'counts': self.counts, 'last_error': self.last_error, 'last_enqueued': self.last_enqueued,
                'minute': state['minute'] if state else None,
                'score': {t: state['statistics'][t]['goals'] for t in ('home', 'away')} if state else None}

    def status(self) -> dict[str, Any]:
        snapshot = None
        if self.role == 'follower':
            try:
                raw = shared.client().get(STATUS_KEY)
                snapshot = json.loads(raw) if raw else None
            except Exception:
                snapshot = None
        base = snapshot or self.local_status()
        return {**base, 'subscribers': len(self.subscribers), 'replica_role': self.role}

    def fan_out(self, message: dict[str, Any]) -> None:
        for queue in list(self.subscribers):
            if queue.full():
                self.subscribers.discard(queue)  # a stalled browser is dropped, not waited for
            else:
                queue.put_nowait(message)

    def _publish(self, message: dict[str, Any]) -> None:
        self.recent.append(message)
        self.fan_out(message)
        if self.role == 'leader' and self.relay is not None:
            self.relay.put_nowait(message)  # relayed to the other replicas in order

    def apply_relayed(self, message: dict[str, Any]) -> None:
        """A follower receives the leader's message: keep it for late joiners and pass it on."""
        if message.get('type') == 'kickoff':
            self.recent.clear()
        self.recent.append(message)
        self.fan_out(message)

    def handle(self, body: dict[str, Any], enqueued: datetime | None = None) -> list[dict[str, Any]]:
        """Apply one message from the hub. Returns the messages fanned out to viewers."""
        from .core import Event
        from .experience import Profile
        from .live import LiveMatch
        self.last_enqueued = enqueued.isoformat() if enqueued else None
        kind = body.get('type')
        if kind == 'kickoff':
            self.run = {'feed_run': body['feed_run'], 'match_id': body['match_id'], 'speed': body.get('speed'),
                        'started': body.get('sent_at'), 'status': 'live', 'source': body.get('source', 'data_feed'),
                        'stats': body.get('stats')}
            self.live = LiveMatch(int(body.get('seed', SEED)), Profile(audience='broadcast'))
            self.counts = {'accepted': 0, 'rejected': 0, 'duplicates': 0, 'moments': 0}
            self.last_error = None
            self.recent.clear()
            out = [{'type': 'kickoff', 'run': self.run}]
        elif self.live is None or self.run is None or body.get('feed_run') != self.run['feed_run']:
            return []  # joined mid-run without its kick-off: wait for the next one
        elif kind == 'full_time':
            self.run['status'] = 'full_time'
            # A video clip covers minutes, not a match: do not close the remaining minutes for it.
            closing = self.live.finish() if self.run.get('source') != 'vision' else []
            out = [*closing, {'type': 'full_time', 'run': self.run}]
        elif kind == 'event':
            data = body['event']
            if data.get('event_id') in self.live.validator.ids:
                self.counts['duplicates'] += 1  # at-least-once delivery: skip, do not fail
                return []
            try:
                out = self.live.ingest(Event(**data))
                self.counts['accepted'] += 1
            except (TypeError, ValueError) as exc:
                self.counts['rejected'] += 1
                self.last_error = f"{data.get('event_id')}: {exc}"[:200]
                out = [{'type': 'rejected', 'event_id': data.get('event_id'), 'reason': self.last_error}]
        else:
            return []
        if self.run and self.run.get('source') == 'vision':
            # Speed and distance tags come from the synthetic physical model, not from the video:
            # a run recovered from video shows only what the video produced.
            out = [m for m in out if not (m.get('type') == 'moment' and m['moment'].get('kind') in PHYSICAL_KINDS)]
        self.counts['moments'] += sum(m.get('type') == 'moment' for m in out)
        for message in out:
            self._publish(message)
        return out


FEED = FeedHub()

LEASE_SECONDS = 15
STATUS_KEY = shared.key('feed', 'status')
RECENT_KEY = shared.key('feed', 'recent')
LEADER_KEY = shared.key('feed', 'leader')
CHANNEL = shared.key('feed', 'messages')


async def run_feed() -> None:
    """The feed task of the API: the consumer on one replica, or lead/follow across replicas."""
    if not shared.enabled():
        await consume()
        return
    while True:
        r = shared.async_client()
        try:
            if await r.set(LEADER_KEY, shared.REPLICA, nx=True, ex=LEASE_SECONDS):
                await lead(r)
            else:
                await follow(r)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Redis unreachable: stand alone until it is back
            FEED.role = 'single'
            log.warning('feed_shared_state_failed error_type=%s', type(exc).__name__)
            await asyncio.sleep(10)
        finally:
            try:
                await r.aclose()
            except Exception:
                pass


async def lead(r, hub: FeedHub | None = None) -> None:
    """Consume the hub and relay to the other replicas while the lease is ours."""
    hub = hub or FEED
    hub.role, hub.relay = 'leader', asyncio.Queue()
    consumer = asyncio.create_task(consume())
    relay = asyncio.create_task(_relay(r, hub))
    try:
        while True:
            await r.set(STATUS_KEY, json.dumps(hub.local_status(), default=str), ex=LEASE_SECONDS * 4)
            await asyncio.sleep(LEASE_SECONDS / 3)
            if await r.get(LEADER_KEY) != shared.REPLICA:
                return  # the lease went elsewhere: step down
            await r.expire(LEADER_KEY, LEASE_SECONDS)
    finally:
        consumer.cancel()
        relay.cancel()
        hub.relay = None


async def _relay(r, hub: FeedHub) -> None:
    while True:
        message = await hub.relay.get()
        body = json.dumps(message, default=str)
        if message.get('type') == 'kickoff':
            await r.delete(RECENT_KEY)
        await r.rpush(RECENT_KEY, body)
        await r.ltrim(RECENT_KEY, -hub.recent.maxlen, -1)
        await r.set(STATUS_KEY, json.dumps(hub.local_status(), default=str), ex=LEASE_SECONDS * 4)
        await r.publish(CHANNEL, body)


async def follow(r, hub: FeedHub | None = None) -> None:
    """Serve viewers from the leader's relay; return when the lease is free, to try for it."""
    hub = hub or FEED
    hub.role = 'follower'
    hub.recent.clear()
    for raw in await r.lrange(RECENT_KEY, 0, -1):
        hub.recent.append(json.loads(raw))
    pubsub = r.pubsub()
    await pubsub.subscribe(CHANNEL)
    try:
        checked = time.monotonic()
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get('type') == 'message':
                hub.apply_relayed(json.loads(message['data']))
            if time.monotonic() - checked > LEASE_SECONDS / 3:
                checked = time.monotonic()
                if not await r.exists(LEADER_KEY):
                    return
    finally:
        try:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass


def credential():
    from azure.identity.aio import DefaultAzureCredential
    return DefaultAzureCredential()


async def consume(replay_minutes: int | None = None, hub: FeedHub | None = None) -> None:
    """Consume the hub forever (reconnecting on failure); a background task of the API."""
    from azure.eventhub.aio import EventHubConsumerClient
    hub = hub or FEED
    replay = int(replay_minutes or os.getenv('FEED_REPLAY_MINUTES', '15'))
    start = datetime.now(timezone.utc) - timedelta(minutes=replay)
    while True:
        cred = credential()

        async def on_event(partition, event):
            if event is None:
                return
            try:
                hub.handle(json.loads(event.body_as_str()), event.enqueued_time)
            except Exception as exc:  # a malformed message must not stop the feed
                hub.counts['rejected'] += 1
                hub.last_error = f'malformed message: {type(exc).__name__}'

        async def on_error(partition, error):
            hub.consumer = {'status': 'error', 'error': type(error).__name__, 'at': time.time()}

        async def on_init(partition):
            hub.consumer = {'status': 'connected', 'partition': partition.partition_id}

        try:
            client = EventHubConsumerClient(fully_qualified_namespace=os.environ['EVENTHUB_NAMESPACE'],
                                            eventhub_name=HUB, consumer_group='$Default', credential=cred)
            async with client:
                await client.receive(on_event, starting_position=start, on_error=on_error,
                                     on_partition_initialize=on_init)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hub.consumer = {'status': 'reconnecting', 'error': type(exc).__name__}
            log.warning('feed_consumer_failed error_type=%s', type(exc).__name__)
            await asyncio.sleep(10)
        finally:
            await cred.close()
        start = datetime.now(timezone.utc) - timedelta(seconds=30)


async def publish(seed: int = SEED, speed: float = 30.0, namespace: str | None = None) -> dict[str, Any]:
    """Publish one synthetic match to the hub in order, at `speed` match seconds per second."""
    from azure.eventhub import EventData
    from azure.eventhub.aio import EventHubProducerClient
    from .core import generate_match
    events = generate_match(seed)
    run = str(uuid4())
    match_id = f'synthetic:{seed}'
    cred = credential()
    producer = EventHubProducerClient(fully_qualified_namespace=namespace or os.environ['EVENTHUB_NAMESPACE'],
                                      eventhub_name=HUB, credential=cred)

    def message(body: dict[str, Any]) -> EventData:
        data = EventData(json.dumps({**body, 'feed_run': run, 'match_id': match_id}))
        data.properties = {'type': body['type'], 'feed_run': run}
        return data

    sent = 0
    try:
        async with producer:
            async def send(bodies):
                nonlocal sent
                # One partition key per match keeps its events in order.
                batch = await producer.create_batch(partition_key=match_id)
                for body in bodies:
                    batch.add(message(body))
                await producer.send_batch(batch)
                sent += len(bodies)

            await send([{'type': 'kickoff', 'seed': seed, 'speed': speed,
                         'sent_at': datetime.now(timezone.utc).isoformat()}])
            pending, previous = [], 0
            for e in events:
                clock = e.minute * 60 + e.second
                if pending and clock - previous >= speed:  # flush about once per real second
                    await send(pending)
                    pending = []
                    await asyncio.sleep((clock - previous) / speed)
                    previous = clock
                pending.append({'type': 'event', 'event': e.json()})
            if pending:
                await send(pending)
            await send([{'type': 'full_time'}])
    finally:
        await cred.close()
    return {'feed_run': run, 'match_id': match_id, 'messages': sent}


async def start_feed_job(job: str | None = None) -> dict[str, Any]:
    """Start a Container Apps Job (the feed producer by default) through Azure Resource Manager,
    with the app's managed identity."""
    import httpx
    job = job or os.environ['FEED_JOB_RESOURCE_ID']
    cred = credential()
    try:
        token = await cred.get_token('https://management.azure.com/.default')
    finally:
        await cred.close()
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post(f'https://management.azure.com{job}/start?api-version=2024-03-01',
                            headers={'Authorization': f'Bearer {token.token}'}, json={})
    if r.status_code >= 300:
        raise RuntimeError(f'job start failed: HTTP {r.status_code}')
    return {'execution': (r.json() or {}).get('name')}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Publish a synthetic match to Azure Event Hubs.')
    parser.add_argument('command', choices=['publish'])
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--speed', type=float, default=float(os.getenv('FEED_SPEED', '30')))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(asyncio.run(publish(args.seed, args.speed))))
