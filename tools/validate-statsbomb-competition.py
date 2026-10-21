"""Run every match of a StatsBomb open-data competition through MatchMind and check it.

Local research only: the provider files stay in backend/data/research (gitignored); this script
prints and optionally writes aggregate results, never provider events.

    python tools/validate-statsbomb-competition.py backend/data/research/statsbomb \
        --dir wc2022 [--out docs/validation/statsbomb-wc2022.json]

For each match: every event the adapter maps must pass MatchMind's validator, and the score
MatchMind computes must equal the official result in the competition's matches file.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core import statistics  # noqa: E402
from app.providers.statsbomb import adapt  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('root', help='folder with matches.json')
    parser.add_argument('--dir', default='.', help='subfolder with events/ and lineups/')
    parser.add_argument('--out')
    args = parser.parse_args()
    root = Path(args.root)
    matches = json.loads((root / 'matches.json').read_text(encoding='utf-8'))
    rows, rejected_reasons, not_represented = [], Counter(), Counter()
    started = time.perf_counter()
    for m in sorted(matches, key=lambda m: (m['match_date'], m['kick_off'] or '')):
        mid = m['match_id']
        events = json.loads((root / args.dir / 'events' / f'{mid}.json').read_text(encoding='utf-8'))
        lineups = json.loads((root / args.dir / 'lineups' / f'{mid}.json').read_text(encoding='utf-8'))
        t0 = time.perf_counter()
        result = adapt(events, lineups, m['home_team']['home_team_id'], match_id=f'statsbomb:{mid}')
        seconds = time.perf_counter() - t0
        report = result['report']
        stats = statistics(result['events'])
        score = [stats['home']['goals'] + report['own_goals']['home'], stats['away']['goals'] + report['own_goals']['away']]
        official = [m['home_score'], m['away_score']]
        for r in report['rejected']:
            rejected_reasons[r['reason']] += 1
        not_represented.update(report['not_represented'])
        rows.append({'match_id': mid, 'date': m['match_date'], 'stage': m['competition_stage']['name'],
                     'match': f"{m['home_team']['home_team_name']} v {m['away_team']['away_team_name']}",
                     'official': official, 'matchmind': score, 'score_agrees': score == official,
                     'own_goals': report['own_goals'], 'source_events': report['source_events'],
                     'accepted': report['accepted'], 'rejected': len(report['rejected']),
                     'stoppage_time_events': report['stoppage_time_events'],
                     'extra_time': any(e.period in (3, 4) for e in result['events']), 'seconds': round(seconds, 2)})
    summary = {
        'competition': f"{matches[0]['competition']['competition_name']} {matches[0]['season']['season_name']}",
        'matches': len(rows), 'scores_agree': sum(r['score_agrees'] for r in rows),
        'matches_with_rejections': sum(r['rejected'] > 0 for r in rows),
        'source_events': sum(r['source_events'] for r in rows), 'accepted': sum(r['accepted'] for r in rows),
        'rejected': sum(r['rejected'] for r in rows), 'rejected_reasons': dict(rejected_reasons.most_common()),
        'own_goals': sum(r['own_goals']['home'] + r['own_goals']['away'] for r in rows),
        'extra_time_matches': sum(r['extra_time'] for r in rows),
        'stoppage_time_events': sum(r['stoppage_time_events'] for r in rows),
        'not_represented': dict(not_represented.most_common()),
        'seconds_total': round(time.perf_counter() - started, 1),
        'seconds_per_match_max': max(r['seconds'] for r in rows),
    }
    print(json.dumps(summary, indent=2))
    for r in rows:
        if not r['score_agrees'] or r['rejected']:
            print('CHECK', r['match'], r['official'], r['matchmind'], 'rejected', r['rejected'])
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({'summary': summary, 'matches': rows}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
