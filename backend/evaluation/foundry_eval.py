"""Release evaluation in Microsoft Foundry.

Generates what MatchMind publishes, with the live agent workflow (Agent Framework on the
Foundry model), then scores it with Azure AI Evaluation and logs the run to the Foundry
project, where it appears under Evaluations:

- Microsoft's AI-assisted evaluators: groundedness (against the verified facts), relevance,
  coherence and fluency, each 1-5;
- MatchMind's own code evaluator, numbers_verified: the share of numbers in the published text
  that appear in the verified facts (1.0 means no unsupported number).

Release thresholds are checked at the end; the exit code is non-zero when one fails, so this
can gate a release in CI. Run (needs backend/.env with a Foundry project and `az login`):

    cd backend && .venv-eval/Scripts/python -m evaluation.foundry_eval --output ../foundry-eval-report.json

Prints scores only; never endpoints, keys or tokens.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND / '.env', override=False)

from app.agents import FoundryAgentRuntime  # noqa: E402
from app.claims import match_claims  # noqa: E402
from app.core import detect_insights, generate_match  # noqa: E402
from app.languages import SUPPORTED  # noqa: E402
from app.recap import recap_facts  # noqa: E402
from app.squads import CLUBS  # noqa: E402

SEED = 20261020
# Style metrics use the SDK's default pass mark (3); groundedness and numbers are the product's
# core promise, so their bars are stricter. Set on 20 October 2026 after the first run.
THRESHOLDS = {'groundedness': 4.0, 'relevance': 3.0, 'coherence': 3.0, 'fluency': 3.0, 'numbers_verified': 1.0}
TASKS = {'recap_half': 'Write a half-time recap of this match for fans in {lang}.',
         'recap_full': 'Write a full-time recap of this match for fans in {lang}.',
         'narrative': 'Explain the latest verified insight about this match to fans in {lang}.'}


def facts_text(events, minute: int, code: str, insights=None) -> str:
    """The verified facts a writer may use, as the context groundedness is judged against."""
    facts = recap_facts(events, minute)
    lines = [f"Clubs: {CLUBS['home'].name} (home) v {CLUBS['away'].name} (away). Minute {minute}.",
             f"Score: {CLUBS['home'].short} {facts['goals']['home']}, {CLUBS['away'].short} {facts['goals']['away']}.",
             'Scorers: ' + ', '.join(f"{s['player']} ({CLUBS[s['team_id']].short}) {s['goals']}" for s in facts['scorers'])]
    lines += [c['statements'][code] for c in match_claims(events, minute)]
    if insights is None:
        # The verified recap record (goal minutes, statistics, player ratings) writers may restate.
        from app.experience import Profile
        from app.recap import build_recap
        lines.append(build_recap(events, SEED, minute, Profile(language=code))['text'])
    for i in insights or []:
        lines.append(json.dumps({k: v for k, v in i.items() if k != 'evidence_event_ids'}, ensure_ascii=False))
    return '\n'.join(lines)


def numbers(text: str) -> set[str]:
    return {n.replace(',', '.').rstrip('.') for n in re.findall(r'\d+(?:[.,]\d+)?', text)}


class NumbersVerified:
    """Code evaluator: every number in the response must appear in the verified facts."""
    def __call__(self, *, response: str, context: str) -> dict:
        found = numbers(response)
        allowed = numbers(context)
        unsupported = sorted(found - allowed)
        return {'numbers_verified': 1.0 if not found else round(1 - len(unsupported) / len(found), 3),
                'unsupported_numbers': ', '.join(unsupported)}


async def generate(concurrency: int) -> list[dict]:
    events = generate_match(SEED)
    insight_minute = 67
    visible = [e for e in events if e.minute < insight_minute]
    insights = detect_insights(visible, insight_minute)
    jobs = []
    for code in SUPPORTED:
        jobs.append(('recap_half', code, 45, lambda c=code: FoundryAgentRuntime().run_recap(events, SEED, 45, c)))
        jobs.append(('recap_full', code, 90, lambda c=code: FoundryAgentRuntime().run_recap(events, SEED, 90, c)))
        jobs.append(('narrative', code, insight_minute,
                     lambda c=code: FoundryAgentRuntime().run(visible, insights, 'fan', c)))
    gate = asyncio.Semaphore(concurrency)

    async def one(kind, code, minute, run):
        async with gate:
            result = await run()
        published = result.narratives[0] if result.narratives else None
        context_insights = insights if kind == 'narrative' else None
        return {'id': f'{kind}:{code}', 'kind': kind, 'language': code,
                'query': TASKS[kind].format(lang=code),
                'response': (published or {}).get('body', ''),
                'context': facts_text(events if kind != 'narrative' else visible, minute, code, context_insights),
                'engine': result.trace.engine, 'live': result.trace.live,
                'fallback_reason': result.trace.fallback_reason or ''}

    return await asyncio.gather(*(one(*job) for job in jobs))


def model_config() -> dict:
    """Judge model: the project's own deployment, reached with Entra ID (no key)."""
    project = os.environ['AZURE_AI_PROJECT_ENDPOINT']
    resource = re.match(r'https://([^.]+)\.services\.ai\.azure\.com', project).group(1)
    return {'azure_endpoint': f'https://{resource}.openai.azure.com', 'api_version': '2024-10-21',
            'azure_deployment': os.environ['AZURE_AI_MODEL_DEPLOYMENT_NAME']}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='../foundry-eval-report.json')
    parser.add_argument('--concurrency', type=int, default=3)
    parser.add_argument('--no-upload', action='store_true', help='score locally without logging to Foundry')
    parser.add_argument('--reuse', action='store_true', help='score the outputs generated by the previous run')
    args = parser.parse_args()

    from azure.ai.evaluation import (CoherenceEvaluator, FluencyEvaluator, GroundednessEvaluator,
                                     RelevanceEvaluator, evaluate)
    from azure.identity import DefaultAzureCredential

    data = BACKEND.parent / '.test-work' / 'foundry-eval-data.jsonl'
    if args.reuse and data.is_file():
        rows = [json.loads(line) for line in data.read_text(encoding='utf-8').splitlines() if line.strip()]
    else:
        rows = asyncio.run(generate(args.concurrency))
        data.parent.mkdir(exist_ok=True)
        data.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
    agent_rows = sum(r['engine'] == 'microsoft_agent_framework' for r in rows)
    print(f'generated {len(rows)} outputs, {agent_rows} published by the agent workflow')

    # Many parallel judge calls fail to connect; a small worker pool is reliable.
    os.environ.setdefault('PF_WORKER_COUNT', '2')
    credential = DefaultAzureCredential()
    config = model_config()
    evaluators = {'groundedness': GroundednessEvaluator(config, credential=credential),
                  'relevance': RelevanceEvaluator(config, credential=credential),
                  'coherence': CoherenceEvaluator(config, credential=credential),
                  'fluency': FluencyEvaluator(config, credential=credential),
                  'numbers_verified': NumbersVerified()}
    mapping = {'query': '${data.query}', 'response': '${data.response}', 'context': '${data.context}'}
    result = evaluate(
        data=str(data), evaluators=evaluators, evaluation_name='matchmind-release-evaluation',
        evaluator_config={name: {'column_mapping': mapping} for name in evaluators},
        azure_ai_project=None if args.no_upload else os.environ['AZURE_AI_PROJECT_ENDPOINT'])

    scores = {}
    for name in THRESHOLDS:
        values = [r.get(f'outputs.{name}.{name}') for r in result['rows']]
        values = [float(v) for v in values if isinstance(v, (int, float))]
        scores[name] = round(mean(values), 3) if values else None
    by_language, by_engine = {}, {}
    for r in result['rows']:
        by_language.setdefault(r['inputs.language'], []).append(r.get('outputs.groundedness.groundedness'))
        engine = 'agent' if r['inputs.engine'] == 'microsoft_agent_framework' else 'verified_fallback'
        for name in ('groundedness', 'fluency'):
            by_engine.setdefault(engine, {}).setdefault(name, []).append(r.get(f'outputs.{name}.{name}'))
    report = {
        'outputs': len(rows), 'published_by_agent_workflow': agent_rows,
        'mean_scores': scores, 'thresholds': THRESHOLDS,
        'passed': {k: scores[k] is not None and scores[k] >= v for k, v in THRESHOLDS.items()},
        'groundedness_by_language': {k: round(mean(float(x) for x in v if x is not None), 2)
                                     for k, v in by_language.items() if any(x is not None for x in v)},
        'by_engine': {e: {n: round(mean(float(x) for x in v if x is not None), 2) for n, v in m.items()}
                      for e, m in by_engine.items()},
        'blocked_by_fact_checker': {r['id']: r['fallback_reason'] for r in rows
                                    if r['engine'] != 'microsoft_agent_framework'},
        'unsupported_numbers': {r['inputs.id']: r['outputs.numbers_verified.unsupported_numbers']
                                for r in result['rows'] if r.get('outputs.numbers_verified.unsupported_numbers')},
        'foundry_run_logged': bool(result.get('studio_url')),
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('mean_scores', 'passed', 'foundry_run_logged')}, indent=2))
    return 0 if all(report['passed'].values()) else 1


if __name__ == '__main__':
    sys.exit(main())
