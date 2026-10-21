"""Load test of the viewer-facing API: concurrent virtual viewers, each requesting what the app
requests while a match plays (experience, graph, tactics, recap, insights) at a random minute.

    python tools/load-test.py https://<app> --users 25 --seconds 60 [--out docs/validation/load-test.json]

Model-backed endpoints (AI recap, Ask the match) are left out: they are rate-limited per visitor
by design and cached, so their cost is bounded separately.
"""
import argparse
import asyncio
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

import httpx

ENDPOINTS = {
    'experience': '/api/experience?minute={m}&language=en&audience=fan',
    'graph_roles': '/api/graph/roles?minute={m}',
    'tactics': '/api/tactics/changes?minute={m}&language=en',
    'recap': '/api/recap?minute={m}&language=en',
    'insights': '/api/insights?minute={m}',
}


async def viewer(client: httpx.AsyncClient, until: float, results: dict) -> None:
    while time.perf_counter() < until:
        name, path = random.choice(list(ENDPOINTS.items()))
        url = path.format(m=random.randint(20, 90))
        started = time.perf_counter()
        try:
            response = await client.get(url)
            ok = response.status_code == 200
        except httpx.HTTPError:
            ok = False
        results[name].append(((time.perf_counter() - started) * 1000, ok))
        await asyncio.sleep(random.uniform(0.2, 1.0))  # a viewer's think time between requests


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--users', type=int, default=25)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--out')
    args = parser.parse_args()
    results: dict[str, list] = defaultdict(list)
    async with httpx.AsyncClient(base_url=args.url.rstrip('/'), timeout=30) as client:
        await client.get('/health')
        until = time.perf_counter() + args.seconds
        await asyncio.gather(*(viewer(client, until, results) for _ in range(args.users)))
    rows = {}
    for name, samples in sorted(results.items()):
        times = [t for t, _ in samples]
        rows[name] = {'requests': len(samples), 'errors': sum(not ok for _, ok in samples),
                      'p50_ms': pct(times, 0.5), 'p95_ms': pct(times, 0.95), 'p99_ms': pct(times, 0.99)}
    every = [t for samples in results.values() for t, _ in samples]
    summary = {'users': args.users, 'seconds': args.seconds, 'requests': len(every),
               'requests_per_second': round(len(every) / args.seconds, 1),
               'errors': sum(r['errors'] for r in rows.values()),
               'p50_ms': pct(every, 0.5), 'p95_ms': pct(every, 0.95), 'p99_ms': pct(every, 0.99),
               'mean_ms': round(statistics.mean(every), 1)}
    print(json.dumps({'summary': summary, 'endpoints': rows}, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps({'summary': summary, 'endpoints': rows}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
