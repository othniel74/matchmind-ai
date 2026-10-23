"""Compare identical synthetic cases: templates, one writer, and the full workflow.

Offline by default. --live explicitly enables paid Azure calls and loads backend/.env.
Checker acceptance is a proxy, not independent factual accuracy or human quality.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core import generate_match
from app.experience import Profile
from app.languages import SUPPORTED
from app.recap import build_recap, recap_facts


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for mode in dict.fromkeys(row['mode'] for row in rows):
        group = [row for row in rows if row['mode'] == mode]
        times = sorted(row['duration_ms'] for row in group if row['status'] != 'error')
        summary[mode] = {
            'runs': len(group), 'errors': sum(r['status'] == 'error' for r in group),
            'fallbacks': sum(r['status'] == 'fallback' for r in group),
            'p50_ms': times[math.ceil(len(times) * .5) - 1] if times else None,
            'p95_ms': times[math.ceil(len(times) * .95) - 1] if times else None,
            'checker_accepted': sum(r.get('checker_accepted') is True for r in group),
            'checker_evaluated': sum(r.get('checker_accepted') is not None for r in group),
            'cost_usd': None,
        }
    return summary


async def compare(seeds, minutes, languages, live=False):
    rows = []
    for seed in seeds:
        events = generate_match(seed)
        for minute in minutes:
            for language in languages:
                case = {'seed': seed, 'minute': minute, 'language': language}
                start = time.perf_counter()
                recap = build_recap(events, seed, minute, Profile(language=language))
                rows.append({**case, 'mode': 'template', 'status': 'ok', 'text': recap['text'],
                             'duration_ms': round((time.perf_counter() - start) * 1000, 2),
                             'checker_accepted': None})
                if not live:
                    continue
                from app.agents import FoundryAgentRuntime
                from app.agent_workflow import (
                    RULES, WriterOutput, _run_agent, check_claims, parse_output, recap_prompt,
                )
                # Separate request-scoped clients prevent the baseline from changing workflow ownership.
                for mode in ('single_agent', 'full_workflow'):
                    runtime = FoundryAgentRuntime()
                    start = time.perf_counter()
                    row = {**case, 'mode': mode, 'checker_accepted': None}
                    try:
                        if mode == 'single_agent':
                            agent = runtime._client().as_agent(
                                name='recap-baseline',
                                instructions='Write a concise football recap from supplied facts only. ' + RULES,
                                default_options={'response_format': WriterOutput},
                            )
                            prompt = recap_prompt(recap_facts(events, minute))
                            row['text'] = parse_output(await _run_agent(
                                agent, prompt + f' Write the final recap in {language}.'))
                            row['status'] = 'ok'
                        else:
                            result = await runtime.run_recap(events, seed, minute, language)
                            row.update(text=result.narratives[0]['body'],
                                       status='ok' if result.trace.live else 'fallback',
                                       fallback_reason=result.trace.fallback_reason,
                                       steps=result.trace.steps)
                        # Exclude the evaluation checker from output-generation latency.
                        row['duration_ms'] = round((time.perf_counter() - start) * 1000, 2)
                        if row['status'] == 'ok':
                            check_start = time.perf_counter()
                            verdict = await check_claims(runtime._client(), row['text'], events, minute, language)
                            row.update(checker_accepted=verdict['publishable'], check=verdict,
                                       check_duration_ms=round((time.perf_counter() - check_start) * 1000, 2))
                    except Exception as exc:
                        row.update(status='error', error_type=type(exc).__name__,
                                   duration_ms=round((time.perf_counter() - start) * 1000, 2))
                    finally:
                        await runtime._close()
                    rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', default='20261020,20261021,20261022')
    parser.add_argument('--minutes', default='45,70,90')
    parser.add_argument('--languages', default='en')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    seeds = [int(s) for s in args.seeds.split(',')]
    minutes = [int(m) for m in args.minutes.split(',')]
    languages = args.languages.split(',')
    if any(s < 0 or s > 2147483647 for s in seeds) or any(m < 20 or m > 90 for m in minutes):
        parser.error('Seeds must be 0..2147483647 and minutes 20..90.')
    if any(language not in SUPPORTED for language in languages):
        parser.error('Unsupported language.')
    if args.live:
        from dotenv import load_dotenv
        from app.agents import selected_provider
        load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
        if selected_provider() is None:
            parser.error('--live needs a configured Azure provider.')
    rows = asyncio.run(compare(seeds, minutes, languages, args.live))
    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(), 'live_requested': args.live,
        'method': 'Same synthetic cases; templates, one writer and full workflow. Sequential, no API cache.',
        'limits': [
            'Checker acceptance uses the product checker, not an independent accuracy assessment.',
            'Templates contain verified numbers; the free-text checker forbids digits, so templates are not scored by it.',
            'Human quality and factual review are pending. Offline timings do not measure model latency.',
            'Cost is unmeasured: reconcile provider usage and billing for an isolated run before reporting it.',
            'Full workflow research requires a running MCP server. Inspect steps for research fallback.',
            'Small samples and execution order can affect latency; repeat before making performance claims.',
        ],
        'summary': summarize(rows), 'runs': rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    return 1 if any(row['status'] == 'error' for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
