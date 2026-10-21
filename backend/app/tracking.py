"""Ground-truth tracking for synthetic broadcast video.

Turns the synthetic event stream into 25 Hz positions for the ball and every player on the
pitch, consistent with the events: the ball is at each event's location at its time, travels
along each pass at the pass's ball speed, and players run (speed-limited) between their team
shape and the actions they take part in. The renderer draws these positions as broadcast video;
the vision pipeline must recover them, and its output is scored against this ground truth.

Units are metres on a 105 x 68 m pitch, origin at the home goal line's bottom corner, x towards
the away goal. Times are match seconds.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any
from .core import Event, ON_BALL_TYPES, SENDING_OFF
from .pitch import FORMATION

LENGTH, WIDTH = 105.0, 68.0
FPS = 25
MAX_RUN = 8.5          # m/s, a player's top running speed in the simulation
DEFAULT_PASS = 14.0    # m/s when an event has no ball speed


def metres(team: str, x: float, y: float) -> tuple[float, float]:
    gx = x if team == 'home' else 100 - x
    return gx / 100 * LENGTH, y / 100 * WIDTH


def event_times(events: list[Event]) -> dict[str, float]:
    """Events share whole seconds; spread each second's events evenly, in sequence order."""
    times: dict[str, float] = {}
    by_second: dict[int, list[Event]] = {}
    for e in events:
        by_second.setdefault(e.minute * 60 + e.second, []).append(e)
    for second, group in by_second.items():
        group.sort(key=lambda e: e.sequence)
        for i, e in enumerate(group):
            times[e.event_id] = second + (i + 0.5) / len(group)
    return times


@dataclass
class Key:
    t: float
    x: float
    y: float
    z: float = 0.0
    owner: str | None = None
    peak: float = 0.0  # arc height of the flight that ends at this key


def ball_keys(events: list[Event], times: dict[str, float]) -> list[Key]:
    """Ball keyframes: at each on-ball event's location, then each pass's flight to its end."""
    on_ball = [e for e in events if e.event_type in ON_BALL_TYPES]
    keys: list[Key] = []
    for i, e in enumerate(on_ball):
        t = times[e.event_id]
        x, y = metres(e.team_id, e.x, e.y)
        if keys and t <= keys[-1].t:
            t = keys[-1].t + 0.04
        keys.append(Key(t, x, y, owner=e.player_id))
        next_t = times[on_ball[i + 1].event_id] if i + 1 < len(on_ball) else t + 3
        if e.event_type == 'pass' and e.end_x is not None:
            ex, ey = metres(e.team_id, e.end_x, e.end_y)
            distance = math.hypot(ex - x, ey - y)
            speed = (e.speed_kmh or DEFAULT_PASS * 3.6) / 3.6
            arrive = min(t + distance / max(speed, 4.0), next_t - 0.08)
            if arrive > t + 0.04:
                owner = e.recipient_player_id if e.outcome == 'success' else None
                keys.append(Key(arrive, ex, ey, owner=owner, peak=min(0.12 * distance, 7.0) if distance > 30 else 0.0))
        elif e.event_type == 'shot':
            goal_x = LENGTH if (e.team_id == 'home') else 0.0
            speed = (e.speed_kmh or 80) / 3.6
            target_y = WIDTH / 2 + (y - WIDTH / 2) * 0.15
            stop_x = goal_x + (1.0 if goal_x else -1.0) if e.outcome == 'goal' else goal_x - (3.0 if goal_x else -3.0)
            distance = math.hypot(stop_x - x, target_y - y)
            arrive = min(t + distance / speed, next_t - 0.08)
            if arrive > t + 0.04:
                keys.append(Key(arrive, stop_x, target_y, owner=None, peak=min(0.04 * distance, 1.6)))
    return keys


def ball_at(keys: list[Key], t: float, cursor: list[int]) -> tuple[float, float, float, str | None]:
    i = cursor[0]
    while i + 1 < len(keys) and keys[i + 1].t <= t:
        i += 1
    cursor[0] = i
    a = keys[i]
    if i + 1 >= len(keys) or t <= a.t:
        return a.x, a.y, 0.0, a.owner
    b = keys[i + 1]
    f = (t - a.t) / (b.t - a.t)
    z = 4 * b.peak * f * (1 - f)
    owner = a.owner if (b.peak == 0 and a.owner and a.owner == b.owner) else None
    return a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f, z, owner


def on_pitch(events: list[Event], t: float, times: dict[str, float]) -> dict[str, str]:
    """Formation slot -> player on the pitch at time t (substitutions and red cards applied)."""
    slots = {f'{team}-{i:02}': f'{team}-{i:02}' for team in ('home', 'away') for i in range(1, 12)}
    slot_of = {p: p for p in slots}
    for e in events:
        if times[e.event_id] > t:
            break
        slot = slot_of.get(e.player_id)
        if slot is None:
            continue
        if e.event_type == 'substitution' and e.replacement_player_id:
            slots[slot] = e.replacement_player_id
            slot_of[e.replacement_player_id] = slot
        elif e.event_type == 'card' and e.outcome in SENDING_OFF:
            slots[slot] = None
    return {s: p for s, p in slots.items() if p}


def track(events: list[Event], start: float, end: float, fps: int = FPS, warmup: float = 20.0) -> dict[str, Any]:
    """Ground-truth tracking for [start, end) match seconds, sampled at `fps`."""
    events = sorted(events, key=lambda e: e.sequence)
    times = event_times(events)
    keys = ball_keys(events, times)
    actions: dict[str, list[tuple[float, float, float]]] = {}
    for k in keys:  # where each player must be, and when: on the ball at each key
        if k.owner:
            actions.setdefault(k.owner, []).append((k.t, k.x, k.y))
    dt = 1.0 / fps
    t = start - warmup  # settle into shape before the clip starts
    cursor = [0]
    positions: dict[str, list[float]] = {}
    frames, team_of = [], {}
    while t < end:
        bx, by, bz, owner = ball_at(keys, t, cursor)
        lineup = on_pitch(events, t, times)
        for slot, pid in lineup.items():
            team = slot.split('-')[0]
            team_of[pid] = team
            fx, fy = FORMATION[int(slot.split('-')[1]) - 1]
            ax, ay = metres(team, fx, fy)
            # The block shifts toward the ball, keepers stay home, the far side compresses.
            if fx > 10:
                ax += (bx - LENGTH / 2) * 0.45
                ay += (by - ay) * 0.22
            seed = sum(map(ord, pid))  # stable across runs, unlike hash()
            ax += 1.2 * math.sin(0.31 * t + seed % 7)
            ay += 1.0 * math.cos(0.27 * t + seed % 5)
            target = (ax, ay)
            for when, x, y in actions.get(pid, ()):
                gap = when - t
                if -0.6 < gap < 4.0:  # run to the ball in time for the action, then release
                    target = (x, y)
                    break
            p = positions.setdefault(pid, [ax, ay])
            dx, dy = target[0] - p[0], target[1] - p[1]
            step = math.hypot(dx, dy)
            limit = MAX_RUN * dt
            if step > limit:
                dx, dy = dx * limit / step, dy * limit / step
            p[0] = min(max(p[0] + dx, -2.0), LENGTH + 2.0)
            p[1] = min(max(p[1] + dy, -2.0), WIDTH + 2.0)
        for pid in list(positions):
            if pid not in lineup.values():
                del positions[pid]
        if owner in positions:  # a close owner carries the ball at their feet
            px, py = positions[owner]
            near = math.hypot(px - bx, py - by)
            if near < 2.5:
                pull = 0.7 * (1 - near / 2.5)
                bx, by = bx + (px - bx) * pull, by + (py - by) * pull
        if t >= start:
            frames.append({'t': round(t, 3), 'ball': [round(bx, 2), round(by, 2), round(bz, 2)], 'owner': owner,
                           'players': {pid: [round(x, 2), round(y, 2)] for pid, (x, y) in positions.items()}})
        t += dt
    clip_events = [{**e.json(), 't': round(times[e.event_id], 3)} for e in events if start <= times[e.event_id] < end]
    return {'fps': fps, 'start': start, 'end': end, 'pitch': {'length': LENGTH, 'width': WIDTH},
            'teams': team_of, 'frames': frames, 'events': clip_events}
