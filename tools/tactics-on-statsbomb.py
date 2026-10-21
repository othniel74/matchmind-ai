"""Tactical change analysis on a real StatsBomb match (local research only; prints findings).

    python tools/tactics-on-statsbomb.py backend/data/research/statsbomb/events.json \
        --lineups backend/data/research/statsbomb/lineups.json --home-team-id 779

Real events are re-timed on one clock of time played (stoppage and extra time included). Shape
measures are left out: they need tracking data, and none is supplied with this match.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import tactics  # noqa: E402
from app.providers.statsbomb import adapt  # noqa: E402
from app.providers.sportmonks import team_names  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('events')
    parser.add_argument('--lineups')
    parser.add_argument('--home-team-id', type=int)
    parser.add_argument('--language', default='en')
    args = parser.parse_args()
    raw = json.loads(Path(args.events).read_text(encoding='utf-8'))
    lineups = json.loads(Path(args.lineups).read_text(encoding='utf-8')) if args.lineups else None
    result = adapt(raw, lineups, args.home_team_id, match_id=f'statsbomb:{Path(args.events).stem}')
    shown = {e.event_id: tactics.scoreboard(e) for e in result['events']}
    events = tactics.played_time(result['events'])
    names = lambda p: result['roster'].get(p, {}).get('name', p)
    clubs = team_names(raw, lineups, args.home_team_id)
    minute = max(e.minute for e in events) + 1
    findings = []
    for point in tactics.change_points(events, minute):
        out = tactics.impact(events, point, minute, args.language, names=names, clubs=clubs, with_shape=False)
        findings.append({'minute': shown[point['event_ids'][0]], 'team': clubs[point['team_id']],
                         'change': out.get('label'), 'available': out['available'],
                         'statements': [s for t in ('home', 'away') for s in out['teams'][t]['statements']]
                         if out['available'] else [out['reason']]})
    print(json.dumps(findings, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
