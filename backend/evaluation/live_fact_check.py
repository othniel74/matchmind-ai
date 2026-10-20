"""Live evaluation of the fact checker against fact_check_cases.json.

Run: cd backend && python -m evaluation.live_fact_check --split test --repeat 2 --output ../fact-check-report.json
Needs a configured model provider (backend/.env). Prints outcomes only; never endpoints or keys.
This is not part of the offline suite because it calls a paid model.
"""
from __future__ import annotations
import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND / '.env', override=False)

from app.agent_workflow import (FACT_CHECKER_INSTRUCTIONS, _run_agent, checker_prompt,  # noqa: E402
                                parse_statements, verify_statements)
from app.agents import FoundryAgentRuntime  # noqa: E402
from app.core import detect_insights, generate_match  # noqa: E402
from evaluation.run import wilson  # noqa: E402

CASES = Path(__file__).with_name('fact_check_cases.json')


async def evaluate(split: str, repeat: int, concurrency: int) -> dict:
    spec = json.loads(CASES.read_text(encoding='utf-8'))
    minute = spec['minute']
    events = [e for e in generate_match() if e.minute < minute]
    insight = detect_insights(events, minute)[0]
    cases = [c for c in spec['cases'] if split == 'all' or c['split'] == split]
    # Each worker owns its client, as each API request does. (Model output still varies between
    # runs even at temperature 0, which is why reports repeat cases and check consistency.)
    runtimes = [FoundryAgentRuntime() for _ in range(concurrency)]
    queue: asyncio.Queue = asyncio.Queue()
    for run in range(repeat):
        for case in cases:
            queue.put_nowait((case, run))
    results: list[dict] = []

    async def check(client, case: dict, run: int) -> dict:
        try:
            agent = client.as_agent(name='fact-checker', instructions=FACT_CHECKER_INSTRUCTIONS,
                                    default_options={'temperature': 0})
            # Same call path as the product: rate-limit responses wait and retry.
            raw = await _run_agent(agent, checker_prompt(case['text']))
            failure, claim_ids, _ = verify_statements(parse_statements(raw), case['text'],
                                                      insight, events)
        except Exception as exc:  # report, never crash the evaluation
            failure, claim_ids = f'error:{type(exc).__name__}', []
        error = str(failure).startswith('error:')
        outcome = 'error' if error else 'pass' if failure is None else 'block'
        # A service error is neither right nor wrong: it is excluded from accuracy and reported.
        return {**case, 'run': run, 'outcome': outcome, 'reason': failure, 'claim_ids': claim_ids,
                'correct': None if error else outcome == case['expect']}

    async def worker(runtime) -> None:
        client = runtime._client()
        while not queue.empty():
            case, run = queue.get_nowait()
            results.append(await check(client, case, run))

    try:
        await asyncio.gather(*(worker(r) for r in runtimes))
    finally:
        for runtime in runtimes:
            if runtime._credential is not None:
                await runtime._credential.close()

    def summary(rows: list[dict]) -> dict:
        rows = [r for r in rows if r['correct'] is not None]
        right = sum(r['correct'] for r in rows)
        return {'correct': right, 'total': len(rows), 'accuracy': round(right / len(rows), 3) if rows else None,
                'ci95': wilson(right, len(rows))}

    groups = defaultdict(lambda: defaultdict(list))
    for row in results:
        for key in ('language', 'category', 'expect'):
            groups[key][row[key]].append(row)
    stable = all(len({r['outcome'] for r in results if r['id'] == c['id'] and r['correct'] is not None}) <= 1
                 for c in cases)
    unsafe = [r for r in results if r['expect'] == 'block' and r['outcome'] == 'pass']
    scored = [r for r in results if r['correct'] is not None]
    return {'split': split, 'repeat': repeat, 'cases': len(cases), 'overall': summary(results),
            'unsafe_passes': summary([r for r in results if r['expect'] == 'block']) | {'count': len(unsafe)},
            'consistent_across_repeats': stable,
            'service_errors': sum(1 for r in results if r['outcome'] == 'error'),
            'rows': [{k: r[k] for k in ('id', 'language', 'category', 'expect', 'outcome', 'reason', 'run')}
                     for r in sorted(results, key=lambda r: (r['id'], r['run']))],
            **{f'by_{k}': {g: summary(v) for g, v in sorted(groups[k].items())} for k in groups},
            'misses': [{k: r[k] for k in ('id', 'language', 'category', 'expect', 'outcome', 'reason', 'text', 'run')}
                       for r in scored if not r['correct']]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=('dev', 'test', 'holdout2', 'holdout3', 'all'), default='test')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--concurrency', type=int, default=4)
    parser.add_argument('--output', default='fact-check-report.json')
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.split, args.repeat, args.concurrency))
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    o = report['overall']
    print(f"{args.split} x{args.repeat}: {o['correct']}/{o['total']} correct ({o['accuracy']}, 95% CI {o['ci95']}); "
          f"wrong statements let through: {report['unsafe_passes']['count']}; "
          f"consistent across repeats: {report['consistent_across_repeats']}; "
          f"service errors: {report['service_errors']}")
    for miss in report['misses']:
        print(f"  MISS {miss['id']} expected {miss['expect']} got {miss['outcome']} ({miss['reason']}): {miss['text']}")


if __name__ == '__main__':
    main()
