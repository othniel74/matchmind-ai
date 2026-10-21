"""Score vision auto-eventing against the renderer's ground truth.

Real broadcast footage has no perfect labels; synthetic video does. Every number here compares
what the pipeline recovered from pixels with what was actually rendered.
"""
from __future__ import annotations
import json
from bisect import bisect_left
from typing import Any

import numpy as np
from .camera import HEIGHT, WIDTH, Camera

MATCH_M = 2.0       # a recovered player within 2 m of a true player is the same detection
EVENT_S = 1.0       # event timing tolerance
EVENT_M = 6.0       # event location tolerance


def _truth_at(tracking, t):
    times = [f['t'] for f in tracking['frames']]
    i = min(max(bisect_left(times, t), 0), len(times) - 1)
    return tracking['frames'][i]


def _visible(camera: Camera, xy: dict[str, list[float]]) -> dict[str, np.ndarray]:
    ids = list(xy)
    if not ids:
        return {}
    uv = camera.project(np.array([[*xy[i], 0.0] for i in ids]))
    out = {}
    for pid, (u, v), p in zip(ids, uv, xy.values()):
        if np.isfinite(u) and 8 <= u < WIDTH - 8 and 20 <= v < HEIGHT - 4:
            out[pid] = np.array(p)
    return out


def evaluate(result: dict[str, Any], tracking: dict[str, Any], cameras: list[dict[str, Any]]) -> dict[str, Any]:
    cam_at = {round(c['t'], 3): c for c in cameras}
    calib, recall_hits, recall_total, pos_err, id_ok, team_ok, matched = [], 0, 0, [], 0, 0, 0
    ball_seen = ball_visible = 0
    ball_err = []
    grid = np.array([[u, v] for u in range(80, WIDTH, 160) for v in range(300, HEIGHT, 80)], float)
    for f in result['frames']:
        c = cam_at.get(round(f['t'], 3))
        if c is None:
            continue
        truth_cam = Camera(c['target'][0], c['target'][1], c['fov'])
        est = Camera(f['camera']['target_x'], f['camera']['target_y'], f['camera']['fov'])
        a, b = truth_cam.to_pitch(grid), est.to_pitch(grid)
        inside = (a[:, 0] > -5) & (a[:, 0] < 110) & (a[:, 1] > -5) & (a[:, 1] < 73)
        calib.append(float(np.median(np.hypot(*(a[inside] - b[inside]).T))))
        truth = _truth_at(tracking, f['t'])
        visible = _visible(truth_cam, truth['players'])
        recall_total += len(visible)
        used = set()
        for pid, p in visible.items():
            best = min(((np.hypot(o['x'] - p[0], o['y'] - p[1]), k) for k, o in enumerate(f['players']) if k not in used),
                       default=(1e9, None))
            if best[0] <= MATCH_M:
                used.add(best[1])
                recall_hits += 1
                o = f['players'][best[1]]
                pos_err.append(best[0])
                matched += 1
                id_ok += o['player_id'] == pid
                team_ok += o['team'] == tracking['teams'].get(pid)
        bx, by, bz = truth['ball']
        if _visible(truth_cam, {'ball': [bx, by]}) and bz < 0.5:
            ball_visible += 1
            if f['ball']:
                ball_seen += 1
                ball_err.append(float(np.hypot(f['ball']['x'] - bx, f['ball']['y'] - by)))

    truth_events = [e for e in tracking['events'] if e['event_type'] in ('pass', 'shot')]
    from app.tracking import metres
    predicted = [e for e in result['events'] if e['type'] in ('pass', 'shot')]
    pairs, used = [], set()
    for te in truth_events:
        tx, ty = metres(te['team_id'], te['x'], te['y'])
        cands = [(abs(pe['t'] - te['t']), k) for k, pe in enumerate(predicted)
                 if k not in used and pe['team'] == te['team_id'] and abs(pe['t'] - te['t']) <= EVENT_S
                 and np.hypot(pe['x'] - tx, pe['y'] - ty) <= EVENT_M]
        if cands:
            _, k = min(cands)
            used.add(k)
            pairs.append((te, predicted[k]))
    tp = len(pairs)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(truth_events) if truth_events else 0.0
    speed_err = [abs(p['speed_kmh'] - t['speed_kmh']) for t, p in pairs if t.get('speed_kmh') and p.get('speed_kmh')]
    goals_true = sum(e['event_type'] == 'shot' and e['outcome'] == 'goal' for e in truth_events)
    goals_found = sum(t['event_type'] == 'shot' and t['outcome'] == 'goal' and p['type'] == 'shot'
                      and p.get('outcome') == 'goal' for t, p in pairs)

    # Physical: compare recovered top speed and distance with the truth over the observed time.
    phys = []
    for pid, m in result['players'].items():
        path = [(f['t'], f['ball']) for f in result['frames']]
        xs = np.array([fr['players'][pid] for fr in tracking['frames'] if pid in fr['players']])
        if len(xs) < 10:
            continue
        step = np.hypot(*np.diff(xs, axis=0).T) * tracking['fps']
        phys.append(abs(m['top_speed_kmh'] - float(np.percentile(step, 95)) * 3.6))

    med = lambda v: round(float(np.median(v)), 3) if v else None
    return {
        'frames_processed': len(result['frames']),
        'calibration_ground_error_m': {'median': med(calib), 'p95': round(float(np.percentile(calib, 95)), 3) if calib else None},
        'player_detection_recall': round(recall_hits / recall_total, 3) if recall_total else None,
        'player_position_error_m': {'median': med(pos_err), 'p95': round(float(np.percentile(pos_err, 95)), 3) if pos_err else None},
        'team_accuracy': round(team_ok / matched, 3) if matched else None,
        'identity_accuracy': round(id_ok / matched, 3) if matched else None,
        'ball_detection_rate': round(ball_seen / ball_visible, 3) if ball_visible else None,
        'ball_position_error_m': med(ball_err),
        'events': {'true': len(truth_events), 'predicted': len(predicted), 'matched': tp,
                   'precision': round(precision, 3), 'recall': round(recall, 3),
                   'f1': round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
                   'passer_correct': round(sum(p['player_id'] == t['player_id'] for t, p in pairs) / tp, 3) if tp else None,
                   'ball_speed_error_kmh': med(speed_err),
                   'goals': {'true': goals_true, 'found': goals_found}},
        'top_speed_error_kmh': med(phys),
    }
