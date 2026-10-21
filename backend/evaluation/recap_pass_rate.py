"""Live publication rate of agent-written recaps: half-time, minute 70 and full time, in every
supported language, on the Foundry model. A recap is published only when the fact checker and
the publication gate pass it; otherwise the verified recap is shown. Rejected statements are
listed by reason, so a regression in the writers or the extractor shows up as a reason count.

    cd backend && .venv-agents/Scripts/python -m evaluation.recap_pass_rate --output ../recap-pass-rate.json

Needs backend/.env with a Foundry project or Azure OpenAI deployment.
"""
import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv


async def run(minutes: list[int]) -> list[dict]:
    from app.agents import FoundryAgentRuntime
    from app.core import DEFAULT_SEED, generate_match
    from app.languages import SUPPORTED
    runtime = FoundryAgentRuntime()
    rows = []
    for minute in minutes:
        for language in SUPPORTED:
            result = await runtime.run_recap(generate_match(), DEFAULT_SEED, minute, language)
            rejected = [v for s in result.trace.steps if s['agent'] == 'fact_checker'
                        for v in s.get('checked', []) if not v['supported']]
            rows.append({'minute': minute, 'language': language, 'published': result.trace.engine == 'microsoft_agent_framework',
                         'fallback_reason': result.trace.fallback_reason,
                         'revised': any(s.get('status') == 'revision_requested' for s in result.trace.steps),
                         'rejected': [{'reason': v['reason'], 'quote': v['quote']} for v in rejected],
                         'duration_ms': result.trace.duration_ms})
            print(minute, language, 'published' if rows[-1]['published'] else f'fallback ({result.trace.fallback_reason})',
                  flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--minutes', default='45,70,90')
    parser.add_argument('--output')
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    rows = asyncio.run(run([int(m) for m in args.minutes.split(',')]))
    summary = {'runs': len(rows), 'published': sum(r['published'] for r in rows),
               'revised_then_published': sum(r['revised'] and r['published'] for r in rows),
               'rejected_statements_by_reason': dict(Counter(x['reason'] for r in rows for x in r['rejected']).most_common())}
    print(json.dumps(summary, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps({'summary': summary, 'runs': rows}, ensure_ascii=False, indent=1),
                                     encoding='utf-8')


if __name__ == '__main__':
    main()
