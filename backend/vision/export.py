"""Export a vision run for the web app: compact overlay frames, truth, events and the scorecard.

    python -m vision.export --result result.json --report report.json --tracking tracking.json \
        --clip <clip dir> --out ../frontend/public/vision
"""
from __future__ import annotations
import argparse
import json
import sys
from bisect import bisect_left
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    from app.squads import name
    from app.tracking import metres
    from vision.to_events import to_match_events
    parser = argparse.ArgumentParser()
    for a in ('--result', '--report', '--tracking', '--clip', '--out'):
        parser.add_argument(a, required=True)
    args = parser.parse_args()
    result = json.loads(Path(args.result).read_text())
    report = json.loads(Path(args.report).read_text())
    tracking = json.loads(Path(args.tracking).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = tracking['start']
    times = [f['t'] for f in tracking['frames']]
    frames = []
    for f in result['frames']:
        truth = tracking['frames'][min(bisect_left(times, f['t']), len(times) - 1)]
        frames.append({
            't': round(f['t'] - start, 2),
            'p': [[round(v) for v in p['box']] + [p['team'][0], p['player_id'].split('-')[1], round(p['x'], 1), round(p['y'], 1)]
                  for p in f['players']],
            'b': [round(f['ball']['u']), round(f['ball']['v'])] if f['ball'] else None,
            'g': [[round(x, 1), round(y, 1), pid[0]] for pid, (x, y) in truth['players'].items()],
            'gb': [round(truth['ball'][0], 1), round(truth['ball'][1], 1)],
        })
    truth_events = [e for e in tracking['events'] if e['event_type'] in ('pass', 'shot')]
    recovered = [e for e in result['events'] if e['type'] in ('pass', 'shot')]
    listed = []
    for e in recovered:
        match = None
        for te in truth_events:
            tx, ty = metres(te['team_id'], te['x'], te['y'])
            if te['team_id'] == e['team'] and abs(te['t'] - e['t']) <= 1.0 and ((tx - e['x']) ** 2 + (ty - e['y']) ** 2) ** .5 <= 6:
                match = te
                break
        listed.append({'t': round(e['t'] - start, 2), 'clock': f"{int(e['t'] // 60):02d}:{int(e['t'] % 60):02d}",
                       'type': e['type'], 'outcome': e.get('outcome', 'success'), 'team': e['team'],
                       'player': name(e['player_id']),
                       'recipient': name(e['recipient_player_id']) if e.get('recipient_player_id') else None,
                       'speed_kmh': e.get('speed_kmh'), 'matched': match is not None,
                       'truth_speed_kmh': match.get('speed_kmh') if match else None,
                       'passer_correct': bool(match and match['player_id'] == e['player_id'])})
    accepted, rejected = to_match_events(result['events'])
    (out / 'overlay.json').write_text(json.dumps({'fps': 25 / result['stride'], 'start': start, 'frames': frames},
                                                 separators=(',', ':')))
    (out / 'events.json').write_text(json.dumps({'recovered': listed, 'truth_count': len(truth_events),
                                                 'validated': len(accepted), 'rejected': rejected}, indent=1))
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(f'overlay {len(frames)} frames, {len(listed)} events ({sum(e["matched"] for e in listed)} matched), '
          f'{len(accepted)} pass MatchMind validation, {len(rejected)} rejected')


if __name__ == '__main__':
    main()
