"""Check Pitchlight's Sportmonks reader on every finished match of a season.

For each match, the score Pitchlight computes from the goal events (goals, penalties, own goals,
shootouts excluded) must equal Sportmonks' official CURRENT score, and both sides must be known.
Disagreements are listed for inspection. Provider data stays local (backend/data/research is
gitignored); only totals are written.

    python tools/validate-sportmonks-season.py --leagues 8,82,564,27 --start 2025-08-01 --end 2026-06-30 \
        [--out docs/validation/sportmonks-2025-26.json]

The token is read from SPORTMONKS_TOKEN (backend/.env), sent in a header, never printed.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.providers.sportmonks import SportmonksError, get, reference  # noqa: E402

INCLUDE = 'participants;scores;events.type;state;league'
FINISHED = {'FT', 'AET', 'FT_PEN'}


def windows(start: date, end: date, days: int = 100):
    """The between endpoint accepts at most 100 days per request."""
    while start <= end:
        stop = min(end, start + timedelta(days=days - 1))
        yield start, stop
        start = stop + timedelta(days=1)


def official(fixture: dict) -> dict[str, int]:
    """Sportmonks' CURRENT score per side (participant 'home'/'away')."""
    out = {}
    for s in fixture.get('scores', []):
        if s.get('description') == 'CURRENT':
            out[s['score']['participant']] = s['score']['goals']
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--leagues', default='8,82,564,27')
    parser.add_argument('--start', default='2025-08-01')
    parser.add_argument('--end', default='2026-06-30')
    parser.add_argument('--out')
    args = parser.parse_args()
    if os.environ.get('MATCHMIND_SKIP_DOTENV') != '1':
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / 'backend' / '.env', override=True)
    token = os.environ.get('SPORTMONKS_TOKEN') or os.environ.get('SPORTMONKS_API_TOKEN')
    if not token:
        raise SystemExit('Set SPORTMONKS_TOKEN in backend/.env')
    fixtures, calls = {}, 0
    for a, b in windows(date.fromisoformat(args.start), date.fromisoformat(args.end)):
        page = 1
        while True:
            try:
                data = get(f'fixtures/between/{a}/{b}', token, include=INCLUDE, filters=f'fixtureLeagues:{args.leagues}',
                           per_page='50', page=str(page))
            except SportmonksError as exc:
                if 'No result' in str(exc) or '404' in str(exc):
                    break
                raise SystemExit(str(exc))
            calls += 1
            for f in data.get('data', []):
                fixtures[f['id']] = f
            remaining = (data.get('rate_limit') or {}).get('remaining')
            if not data.get('pagination', {}).get('has_more'):
                break
            page += 1
            if remaining is not None and remaining < 5:
                raise SystemExit(f'Rate limit nearly used ({remaining} left); try again later')
        time.sleep(0.2)
    rows, problems = [], []
    for f in fixtures.values():
        state = (f.get('state') or {}).get('developer_name')
        if state not in FINISHED:
            continue
        ref = reference(f)
        truth = official(f)
        sides_known = set(ref['teams']) == {'home', 'away'}
        agrees = sides_known and ref['score'] == truth
        kinds = Counter((e.get('type') or {}).get('developer_name') for e in f.get('events', []))
        row = {'id': f['id'], 'league': (f.get('league') or {}).get('name'), 'date': f.get('starting_at', '')[:10],
               'match': f.get('name'), 'state': state, 'official': truth, 'pitchlight': ref['score'], 'agrees': agrees,
               'own_goals': kinds.get('OWNGOAL', 0), 'penalties': kinds.get('PENALTY', 0),
               'shootout_events': sum(n for k, n in kinds.items() if k and 'SHOOTOUT' in k)}
        rows.append(row)
        if not agrees:
            problems.append(row)
    by_league = Counter(r['league'] for r in rows)
    summary = {'calls': calls, 'matches': len(rows), 'scores_agree': sum(r['agrees'] for r in rows),
               'by_league': dict(by_league), 'own_goals': sum(r['own_goals'] for r in rows),
               'penalty_goals': sum(r['penalties'] for r in rows),
               'matches_with_shootouts': sum(r['shootout_events'] > 0 for r in rows),
               'states': dict(Counter(r['state'] for r in rows))}
    print(json.dumps(summary, indent=2))
    for p in problems[:40]:
        print('CHECK', p['league'], p['date'], p['match'], p['state'], 'official', p['official'], 'pitchlight', p['pitchlight'])
    Path('backend/data/research/sportmonks-season-raw.json').write_text(
        json.dumps(list(fixtures.values()), ensure_ascii=False), encoding='utf-8')
    if args.out:
        Path(args.out).write_text(json.dumps({'summary': summary, 'disagreements': problems}, indent=2,
                                             ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
