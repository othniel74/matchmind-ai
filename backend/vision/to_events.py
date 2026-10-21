"""Recovered vision events -> standard Pitchlight events (the same contract as any data feed).

Coordinates become team-relative 0-100 (each team attacking left to right), times become match
clock minute and second, and every event is checked by the same StreamValidator a provider feed
would be. Events that would fail validation are reported, not silently dropped.
"""
from __future__ import annotations
from typing import Any

L, W = 105.0, 68.0


def relative(team: str, x: float, y: float) -> tuple[float, float]:
    gx = x / L * 100
    return round(min(max(gx if team == 'home' else 100 - gx, 0.0), 100.0), 1), round(min(max(y / W * 100, 0.0), 100.0), 1)


def to_match_events(recovered: list[dict[str, Any]], match_id: str = 'vision:clip') -> tuple[list[dict], list[dict]]:
    from app.core import Event, StreamValidator
    validator = StreamValidator()
    accepted, rejected = [], []
    previous = (-1, -1)
    sequence = 0
    for i, r in enumerate(recovered):
        minute, second = int(r['t'] // 60), int(r['t'] % 60)
        if (minute, second) < previous:
            continue
        previous = (minute, second)
        sequence += 1
        x, y = relative(r['team'], r['x'], r['y'])
        data = {'event_id': f'vis-{sequence:05d}', 'match_id': match_id, 'sequence': sequence, 'minute': minute,
                'second': second, 'team_id': r['team'], 'player_id': r['player_id'], 'event_type': r['type'],
                'x': x, 'y': y, 'outcome': r.get('outcome', 'success'),
                'possession_id': f'vis-poss-{sequence:05d}'}
        if r['type'] == 'pass':
            ex, ey = relative(r['team'], r['end_x'], r['end_y'])
            data.update(end_x=ex, end_y=ey, recipient_player_id=r.get('recipient_player_id'))
        if r['type'] in ('pass', 'shot') and r.get('speed_kmh'):
            data['speed_kmh'] = min(max(r['speed_kmh'], 0.1), 140.0)
        try:
            event = Event(**data)
            validator.add(event)
            accepted.append({**data, 'source': 'vision', 't': r['t']})
        except (TypeError, ValueError) as exc:
            rejected.append({'event': data, 'reason': str(exc)})
    return accepted, rejected
