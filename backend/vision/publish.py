"""Video -> events -> Azure Event Hubs: the vision job (Container Apps Job `matchmind-vision`).

Processes a broadcast clip with the vision pipeline, converts what it recovers into validated
MatchMind events, and publishes them to the match feed as a run whose source is 'vision', so the
app ingests video-derived events exactly as it would a data provider's feed.

    python -m vision.publish --video /app/clip/clip.mp4 --start 450 --stride 5
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def publish(events: list[dict], stats: dict, namespace: str, hub: str = 'match-events') -> dict:
    from azure.eventhub import EventData
    from azure.eventhub.aio import EventHubProducerClient
    from azure.identity.aio import DefaultAzureCredential
    run = str(uuid4())
    match_id = 'vision:clip'
    bodies = [{'type': 'kickoff', 'seed': 20261020, 'source': 'vision', 'stats': stats,
               'sent_at': datetime.now(timezone.utc).isoformat()}]
    bodies += [{'type': 'event', 'event': {k: v for k, v in e.items() if k not in ('source', 't')}} for e in events]
    bodies.append({'type': 'full_time'})
    cred = DefaultAzureCredential()
    try:
        async with EventHubProducerClient(fully_qualified_namespace=namespace, eventhub_name=hub, credential=cred) as producer:
            for i in range(0, len(bodies), 50):
                batch = await producer.create_batch(partition_key=match_id)
                for body in bodies[i:i + 50]:
                    batch.add(EventData(json.dumps({**body, 'feed_run': run, 'match_id': match_id})))
                await producer.send_batch(batch)
                await asyncio.sleep(0.5)  # let viewers watch the recovered events arrive
    finally:
        await cred.close()
    return {'feed_run': run, 'messages': len(bodies)}


def main() -> None:
    from vision.pipeline import run
    from vision.to_events import to_match_events
    from app.core import generate_match
    from app.tracking import track
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', required=True)
    parser.add_argument('--start', type=float, default=450.0)
    parser.add_argument('--stride', type=int, default=5)
    parser.add_argument('--namespace', default=os.getenv('EVENTHUB_NAMESPACE'))
    args = parser.parse_args()
    # The team sheet (who plays, for which team) is the only match information given to the pipeline.
    teams = track(generate_match(), args.start, args.start + 1)['teams']
    lineups = {t: sorted(p for p, team in teams.items() if team == t)[:11] for t in ('home', 'away')}
    began = time.perf_counter()
    result = run(Path(args.video), lineups, args.start, 25.0, args.stride)
    accepted, rejected = to_match_events(result['events'])
    stats = {'frames': len(result['frames']), 'seconds': round(time.perf_counter() - began, 1),
             'recovered': len(result['events']), 'validated': len(accepted), 'rejected': len(rejected)}
    print(json.dumps(stats))
    if args.namespace:
        print(json.dumps(asyncio.run(publish(accepted, stats, args.namespace))))


if __name__ == '__main__':
    main()
