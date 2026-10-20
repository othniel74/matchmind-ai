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
separate checkpoint store is needed for this single-replica consumer.

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

log = logging.getLogger('matchmind.feed')
HUB = os.getenv('EVENTHUB_NAME', 'match-events')
SEED = 20261020


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

    def status(self) -> dict[str, Any]:
        state = self.live.state() if self.live is not None else None
        return {'enabled': enabled(), 'consumer': self.consumer, 'hub': HUB, 'run': self.run,
                'counts': self.counts, 'last_error': self.last_error, 'last_enqueued': self.last_enqueued,
                'minute': state['minute'] if state else None,
                'score': {t: state['statistics'][t]['goals'] for t in ('home', 'away')} if state else None,
                'subscribers': len(self.subscribers)}

    def _publish(self, message: dict[str, Any]) -> None:
        self.recent.append(message)
        for queue in list(self.subscribers):
            if queue.full():
                self.subscribers.discard(queue)  # a stalled browser is dropped, not waited for
            else:
                queue.put_nowait(message)

    def handle(self, body: dict[str, Any], enqueued: datetime | None = None) -> list[dict[str, Any]]:
        """Apply one message from the hub. Returns the messages fanned out to viewers."""
        from .core import Event
        from .experience import Profile
        from .live import LiveMatch
        self.last_enqueued = enqueued.isoformat() if enqueued else None
        kind = body.get('type')
        if kind == 'kickoff':
            self.run = {'feed_run': body['feed_run'], 'match_id': body['match_id'], 'speed': body.get('speed'),
                        'started': body.get('sent_at'), 'status': 'live'}
            self.live = LiveMatch(int(body.get('seed', SEED)), Profile(audience='broadcast'))
            self.counts = {'accepted': 0, 'rejected': 0, 'duplicates': 0, 'moments': 0}
            self.last_error = None
            self.recent.clear()
            out = [{'type': 'kickoff', 'run': self.run}]
        elif self.live is None or self.run is None or body.get('feed_run') != self.run['feed_run']:
            return []  # joined mid-run without its kick-off: wait for the next one
        elif kind == 'full_time':
            self.run['status'] = 'full_time'
            out = [*self.live.finish(), {'type': 'full_time', 'run': self.run}]
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
        self.counts['moments'] += sum(m.get('type') == 'moment' for m in out)
        for message in out:
            self._publish(message)
        return out


FEED = FeedHub()


def credential():
    from azure.identity.aio import DefaultAzureCredential
    return DefaultAzureCredential()


async def consume(replay_minutes: int | None = None) -> None:
    """Consume the hub forever (reconnecting on failure); a background task of the API."""
    from azure.eventhub.aio import EventHubConsumerClient
    replay = int(replay_minutes or os.getenv('FEED_REPLAY_MINUTES', '15'))
    start = datetime.now(timezone.utc) - timedelta(minutes=replay)
    while True:
        cred = credential()

        async def on_event(partition, event):
            if event is None:
                return
            try:
                FEED.handle(json.loads(event.body_as_str()), event.enqueued_time)
            except Exception as exc:  # a malformed message must not stop the feed
                FEED.counts['rejected'] += 1
                FEED.last_error = f'malformed message: {type(exc).__name__}'

        async def on_error(partition, error):
            FEED.consumer = {'status': 'error', 'error': type(error).__name__, 'at': time.time()}

        async def on_init(partition):
            FEED.consumer = {'status': 'connected', 'partition': partition.partition_id}

        try:
            client = EventHubConsumerClient(fully_qualified_namespace=os.environ['EVENTHUB_NAMESPACE'],
                                            eventhub_name=HUB, consumer_group='$Default', credential=cred)
            async with client:
                await client.receive(on_event, starting_position=start, on_error=on_error,
                                     on_partition_initialize=on_init)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            FEED.consumer = {'status': 'reconnecting', 'error': type(exc).__name__}
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


async def start_feed_job() -> dict[str, Any]:
    """Start the producer job through Azure Resource Manager with the app's managed identity."""
    import httpx
    job = os.environ['FEED_JOB_RESOURCE_ID']
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
