"""Broadcast video -> tracked players and ball in pitch metres -> match events.

Stages (after SoccerNet Game State Reconstruction):
1. detect players (RT-DETR, a transformer real-time detector) and the ball (small round white blobs);
2. calibrate the camera from the pitch lines and project feet and ball onto the pitch;
3. split teams by kit colour, matched to the team sheet's kit colours;
4. track identities: each team's eleven formation slots, seeded from the announced line-up,
   are matched to detections every frame (Hungarian assignment on predicted positions);
5. derive events: possession from ball-player proximity, passes, interceptions and shots, with
   ball speed from the ball's flight, and every player's speed and distance from their track.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from .calibrate import Calibrator, line_mask
from .camera import HEIGHT, L, W, WIDTH, Camera

FORMATION = ((8, 50), (25, 14), (23, 38), (23, 62), (25, 86), (44, 25), (42, 50), (44, 75), (65, 16), (68, 50), (65, 84))
POSSESSION_M = 2.0
MIN_PASS_KMH = 8.0  # a pass travels; slower ball movement between players is a contest (favours precision)
GATE_M = 3.0


class PersonDetector:
    def __init__(self, name: str = 'PekingU/rtdetr_r50vd', width: int = 640, height: int = 640, threshold: float = 0.3):
        import torch
        from transformers import RTDetrForObjectDetection, RTDetrImageProcessor
        self.torch = torch
        self.proc = RTDetrImageProcessor.from_pretrained(name, size={'height': height, 'width': width})
        self.model = RTDetrForObjectDetection.from_pretrained(name).eval()
        self.person = [k for k, v in self.model.config.id2label.items() if v == 'person'][0]
        self.threshold = threshold

    def __call__(self, bgr: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        with self.torch.no_grad():
            out = self.model(**self.proc(images=rgb, return_tensors='pt'))
        r = self.proc.post_process_object_detection(out, target_sizes=self.torch.tensor([rgb.shape[:2]]),
                                                    threshold=self.threshold)[0]
        keep = r['labels'] == self.person
        boxes = r['boxes'][keep].numpy()
        scores = r['scores'][keep].numpy()
        return nms(boxes, scores, 0.5)


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> np.ndarray:
    order, keep = scores.argsort()[::-1], []
    while len(order):
        i = order[0]
        keep.append(i)
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0]); yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2]); yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area = lambda b: (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])
        order = rest[inter / (area(boxes[i]) + area(boxes[rest]) - inter + 1e-6) < iou]
    return boxes[keep]


def kit_colour(bgr: np.ndarray, box: np.ndarray) -> np.ndarray | None:
    """Median HSV of the shirt: upper body, centre of the box, grass pixels removed."""
    x1, y1, x2, y2 = box
    h, w = y2 - y1, x2 - x1
    crop = bgr[int(y1 + 0.18 * h):int(y1 + 0.5 * h), int(x1 + 0.25 * w):int(x2 - 0.25 * w)]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)
    shirt = hsv[~((hsv[:, 0] > 35) & (hsv[:, 0] < 85) & (hsv[:, 1] > 70)) & (hsv[:, 2] > 60)]
    return np.median(shirt, axis=0) if len(shirt) >= 4 else None


def hue_point(hsv: np.ndarray) -> np.ndarray:
    """Shirt colour as a point: hue on a circle scaled by saturation, plus brightness."""
    h, sat, v = hsv
    angle = 2 * np.pi * h / 180.0
    return np.array([np.cos(angle) * sat, np.sin(angle) * sat, 0.35 * v])


class TeamModel:
    """Kit colours clustered from the clip itself, then named with the team sheet.

    Lighting changes how kits look (a white shirt in shade reads as tan), so fixed colour
    thresholds fail. Two clusters are found from all players seen; the one whose hue is closer
    to the away kit's sky blue is the away team. Goalkeepers' kits are strongly saturated."""
    AWAY_HUE = 104.0

    def __init__(self, colours: list[np.ndarray]):
        pts = np.array([hue_point(c) for c in colours])
        centres = pts[np.argsort(pts[:, 1])[[len(pts) // 5, 4 * len(pts) // 5]]]
        for _ in range(30):
            label = np.argmin(np.linalg.norm(pts[:, None] - centres[None], axis=2), axis=1)
            centres = np.array([pts[label == k].mean(axis=0) if (label == k).any() else centres[k] for k in (0, 1)])
        hues = []
        for k in (0, 1):
            members = np.array(colours)[label == k]
            angle = np.arctan2(np.sin(2 * np.pi * members[:, 0] / 180).mean(), np.cos(2 * np.pi * members[:, 0] / 180).mean())
            hues.append((angle * 180 / (2 * np.pi)) % 180)
        away = int(np.argmin([min(abs(h - self.AWAY_HUE), 180 - abs(h - self.AWAY_HUE)) for h in hues]))
        self.centres, self.names = centres, {away: 'away', 1 - away: 'home'}
        spread = np.linalg.norm(pts - centres[label], axis=1)
        self.limit = float(np.percentile(spread, 95)) * 1.6

    def __call__(self, hsv: np.ndarray | None) -> tuple[str | None, bool]:
        if hsv is None:
            return None, False
        h, sat, _ = hsv
        if sat >= 95 and 15 <= h <= 35:
            return 'home', True   # yellow goalkeeper
        if sat >= 60 and 120 <= h <= 165:
            return 'away', True   # purple goalkeeper
        d = np.linalg.norm(self.centres - hue_point(hsv), axis=1)
        k = int(np.argmin(d))
        return (self.names[k], False) if d[k] <= self.limit else (None, False)


BALL_RADIUS = 0.16  # metres, as rendered


def ball_candidates(bgr: np.ndarray, lines: np.ndarray, boxes: np.ndarray,
                    camera: Camera | None = None) -> list[tuple[float, float, float]]:
    """Small, round, white blobs of the size a ball would have at that point on the pitch:
    (u, v, score). Painted lines, player bodies and goal frames are rejected."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    white = ((hsv[:, :, 1] < 70) & (hsv[:, :, 2] > 175)).astype(np.uint8)
    white[cv2.dilate(lines, np.ones((3, 3), np.uint8)) > 0] = 0
    n, _, stats, centres = cv2.connectedComponentsWithStats(white, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 3 or max(w, h) > 18 or max(w, h) > 1.6 * min(w, h) or area / float(w * h) < 0.5:
            continue  # not round: line fragments, posts, kit patches
        u, v = centres[i]
        if any(b[0] - 2 <= u <= b[2] + 2 and b[1] - 2 <= v <= b[1] + 0.85 * (b[3] - b[1]) for b in boxes):
            continue  # on a player's body, not at their feet
        fit = 1.0
        if camera is not None:  # expected apparent size of a ball lying at this point
            p = camera.to_pitch(np.array([[u, v]]))[0]
            uv = camera.project(np.array([[p[0], p[1], 0.0], [p[0], p[1], 2 * BALL_RADIUS]]))
            expected = float(np.hypot(*(uv[0] - uv[1]))) if np.isfinite(uv).all() else 0.0
            if expected <= 0:
                continue
            ratio = max(w, h) / expected
            if not 0.45 <= ratio <= 2.2:
                continue
            fit = 1.0 - min(abs(np.log(ratio)), 1.0)
        out.append((float(u), float(v), fit))
    return out


@dataclass
class Slot:
    player_id: str
    team: str
    pos: np.ndarray
    vel: np.ndarray = field(default_factory=lambda: np.zeros(2))
    seen: float = -1e9
    path: list = field(default_factory=list)  # (t, x, y) when observed


def anchor(team: str, fx: float, fy: float) -> np.ndarray:
    gx = fx if team == 'home' else 100 - fx
    return np.array([gx / 100 * L, fy / 100 * W])


def observe(image: np.ndarray, t: float, calibrator: Calibrator, detector: PersonDetector) -> dict[str, Any]:
    """Everything the slow models see in one frame, cached so later stages can be re-run."""
    camera, quality = calibrator(image)
    boxes = detector(image)
    feet = np.array([[(b[0] + b[2]) / 2, b[3]] for b in boxes]) if len(boxes) else np.zeros((0, 2))
    pitch = camera.to_pitch(feet) if len(feet) else np.zeros((0, 2))
    colours = [kit_colour(image, b) for b in boxes]
    balls = []
    candidates = ball_candidates(image, line_mask(image), boxes, camera)
    if candidates:
        pts = camera.to_pitch(np.array([[u, v] for u, v, _ in candidates]))
        balls = [[u, v, fit, float(x), float(y)] for (u, v, fit), (x, y) in zip(candidates, pts)]
    return {'t': t, 'camera': {'target_x': camera.target_x, 'target_y': camera.target_y, 'fov': camera.fov,
                               'quality': quality},
            'players': [{'box': [float(v) for v in b], 'x': float(x), 'y': float(y),
                         'colour': None if c is None else [float(v) for v in c]}
                        for b, (x, y), c in zip(boxes, pitch, colours)],
            'balls': balls}


class Assembler:
    """Teams, identities, ball and events from cached observations."""

    def __init__(self, lineups: dict[str, list[str]], fps: float, observations: list[dict[str, Any]]):
        self.fps = fps
        self.slots = [Slot(pid, team, anchor(team, *FORMATION[i]))
                      for team, players in lineups.items() for i, pid in enumerate(players)]
        colours = [np.array(p['colour']) for o in observations for p in o['players'] if p['colour'] is not None]
        self.teams = TeamModel(colours)
        self.offset = {'home': np.zeros(2), 'away': np.zeros(2)}  # where each team's block sits vs its formation
        self.anchor = {s.player_id: s.pos.copy() for s in self.slots}
        self.ball: np.ndarray | None = None
        self.ball_vel = np.zeros(2)
        self.frames: list[dict[str, Any]] = []

    def _predict(self, slot: Slot, t: float) -> tuple[np.ndarray, float]:
        """Where a player should be, and how far to look: recently seen players move on with their
        velocity; players out of view are expected at their place in the team's current shape."""
        shape = self.anchor[slot.player_id] + self.offset[slot.team]
        if slot.seen < -1e8:
            return shape, 14.0
        age = t - slot.seen
        motion = slot.pos + slot.vel * min(age, 1.0)
        if age <= 1.0:
            return motion, GATE_M + MAX_GATE_GROWTH * age
        w = min((age - 1.0) / 4.0, 1.0)  # hand over from motion to team shape over a few seconds
        return (1 - w) * motion + w * shape, min(GATE_M + MAX_GATE_GROWTH * age, 14.0)

    def _assign(self, team: str, points: np.ndarray, t: float) -> dict[int, Slot]:
        slots = [s for s in self.slots if s.team == team]
        if not len(points):
            return {}
        predicted, gates = zip(*(self._predict(s, t) for s in slots))
        cost = np.linalg.norm(points[:, None, :] - np.array(predicted)[None, :, :], axis=2)
        cost = np.where(cost <= np.array(gates)[None, :], cost, 1e6)
        rows, cols = linear_sum_assignment(cost)
        matches = {r: slots[c] for r, c in zip(rows, cols) if cost[r, c] < 1e6}
        if matches:  # the team block follows the players actually seen
            shift = np.median([points[r] - self.anchor[sl.player_id] for r, sl in matches.items()], axis=0)
            self.offset[team] = 0.7 * self.offset[team] + 0.3 * shift
        return matches

    def step(self, o: dict[str, Any]) -> dict[str, Any]:
        t = o['t']
        observed = []
        for team in ('home', 'away'):
            idx = [i for i, p in enumerate(o['players'])
                   if -3 <= p['x'] <= L + 3 and -3 <= p['y'] <= W + 3
                   and self.teams(None if p['colour'] is None else np.array(p['colour']))[0] == team]
            points = np.array([[o['players'][i]['x'], o['players'][i]['y']] for i in idx]) if idx else np.zeros((0, 2))
            for r, slot in self._assign(team, points, t).items():
                p = points[r]
                if slot.seen > -1e8 and t > slot.seen:
                    slot.vel = 0.6 * slot.vel + 0.4 * (p - slot.pos) / (t - slot.seen)
                slot.pos = 0.65 * p + 0.35 * (slot.pos + slot.vel * (t - slot.seen) if slot.seen > -1e8 else p)
                slot.seen = t
                slot.path.append((t, float(slot.pos[0]), float(slot.pos[1])))
                observed.append({'player_id': slot.player_id, 'team': team, 'x': float(slot.pos[0]),
                                 'y': float(slot.pos[1]), 'box': o['players'][idx[r]]['box']})
        frame = {'t': t, 'camera': o['camera'], 'players': observed, 'ball': self._ball(o['balls']),
                 'detections': len(o['players'])}
        self.frames.append(frame)
        return frame

    def _ball(self, balls):
        spots = np.array([[L / 2, W / 2], [11.0, W / 2], [L - 11.0, W / 2]])
        keep = [b for b in balls if -1.5 <= b[3] <= L + 1.5 and -1.5 <= b[4] <= W + 1.5
                and np.min(np.hypot(spots[:, 0] - b[3], spots[:, 1] - b[4])) > 0.8]
        if not keep:
            return None
        points = np.array([[b[3], b[4]] for b in keep])
        if self.ball is not None:
            d = np.linalg.norm(points - (self.ball + self.ball_vel / self.fps), axis=1)
            j = int(np.argmin(d))
            if d[j] > 12:
                return None
        else:
            j = int(np.argmax([b[2] for b in keep]))
        p = points[j]
        if self.ball is not None:
            self.ball_vel = 0.5 * self.ball_vel + 0.5 * (p - self.ball) * self.fps
        self.ball = p
        return {'x': float(p[0]), 'y': float(p[1]), 'u': keep[j][0], 'v': keep[j][1]}


MAX_GATE_GROWTH = 1.5  # metres of extra gate per second unseen


def derive_events(frames: list[dict[str, Any]], match_id: str = 'vision') -> list[dict[str, Any]]:
    """Possession, passes, interceptions and shots from tracked players and ball."""
    owners = []  # (t, player_id, team, ball xy)
    for f in frames:
        if not f['ball']:
            continue
        b = np.array([f['ball']['x'], f['ball']['y']])
        near = sorted(((np.hypot(p['x'] - b[0], p['y'] - b[1]), p) for p in f['players']), key=lambda x: x[0])
        if near and near[0][0] <= POSSESSION_M:
            owners.append((f['t'], near[0][1]['player_id'], near[0][1]['team'], b))
    # Possession spells: consecutive frames with the same owner.
    spells = []
    for t, pid, team, b in owners:
        if spells and spells[-1]['player_id'] == pid and t - spells[-1]['end'] < 0.8:
            spells[-1]['end'], spells[-1]['end_xy'] = t, b
        else:
            spells.append({'player_id': pid, 'team': team, 'start': t, 'end': t, 'start_xy': b, 'end_xy': b})
    spells = [s for s in spells if s['end'] - s['start'] >= 0.08 or True]
    path = [(f['t'], f['ball']['x'], f['ball']['y']) for f in frames if f['ball']]

    def flight_speed(t0: float, t1: float, fallback: float) -> float:
        # Ball speed from the ball's observed flight, not from the gap between possessions
        # (which also counts the time before the receiver is recognised).
        flight = [(t, x, y) for t, x, y in path if t0 <= t <= t1]
        steps = [np.hypot(x2 - x1, y2 - y1) / (t2 - t1_) for (t1_, x1, y1), (t2, x2, y2) in zip(flight, flight[1:])
                 if 0 < t2 - t1_ <= 0.5]
        return float(np.percentile(steps, 75)) * 3.6 if len(steps) >= 2 else fallback

    events = []
    for a, b in zip(spells, spells[1:]):
        if a['player_id'] == b['player_id']:
            continue
        flight = max(b['start'] - a['end'], 1e-3)
        distance = float(np.hypot(*(b['start_xy'] - a['end_xy'])))
        if distance < 2.0:
            continue  # a tackle-like change at close range, not a pass
        speed = flight_speed(a['end'], b['start'], distance / flight * 3.6)
        if speed < MIN_PASS_KMH:
            continue  # the ball barely moved: a contest or a touch between close players, not a pass
        events.append({'type': 'pass', 't': a['end'], 'team': a['team'], 'player_id': a['player_id'],
                       'recipient_player_id': b['player_id'] if b['team'] == a['team'] else None,
                       'outcome': 'success' if b['team'] == a['team'] else 'failed',
                       'x': float(a['end_xy'][0]), 'y': float(a['end_xy'][1]),
                       'end_x': float(b['start_xy'][0]), 'end_y': float(b['start_xy'][1]),
                       'speed_kmh': round(min(speed, 140.0), 1), 'distance_m': round(distance, 1)})
        if b['team'] != a['team']:
            events.append({'type': 'recovery', 't': b['start'], 'team': b['team'], 'player_id': b['player_id'],
                           'x': float(b['start_xy'][0]), 'y': float(b['start_xy'][1])})
    # Shots: the ball leaves a player fast towards a goal and ends near the goal line.
    for s in spells:
        after = [(t, x, y) for t, x, y in path if s['end'] < t <= s['end'] + 2.0]
        if len(after) < 3:
            continue
        goal_x = L if s['team'] == 'home' else 0.0
        t1, x1, y1 = after[-1]
        speed = np.hypot(x1 - s['end_xy'][0], y1 - s['end_xy'][1]) / max(t1 - s['end'], 1e-3) * 3.6
        toward = abs(x1 - goal_x) < abs(s['end_xy'][0] - goal_x) - 5
        if speed > 40 and toward and abs(x1 - goal_x) < 4:
            goal = (x1 > L - 0.3 if goal_x else x1 < 0.3) and abs(y1 - W / 2) < 3.66
            events.append({'type': 'shot', 't': s['end'], 'team': s['team'], 'player_id': s['player_id'],
                           'x': float(s['end_xy'][0]), 'y': float(s['end_xy'][1]), 'outcome': 'goal' if goal else 'saved',
                           'speed_kmh': round(float(speed), 1)})
    # Goals: the ball seen beyond a goal line between the posts. A close-range finish can cross
    # in less than one sampled frame, so this does not depend on seeing the shot's flight.
    goal_times = {round(e['t'], 1) for e in events if e['type'] == 'shot' and e['outcome'] == 'goal'}
    for t, x, y in path:
        if not (x < -0.2 or x > L + 0.2) or abs(y - W / 2) > 3.66 + 0.3:
            continue
        scoring = 'away' if x < 0 else 'home'
        if any(abs(t - g) < 10 for g in goal_times):
            continue
        # The ball is often hidden at the scorer's feet until the finish, so the shot is placed just
        # before the ball is first seen over the line, from where the ball was last seen on the pitch,
        # and credited to the scoring team's player nearest that spot.
        seen = [(bt, bx, by) for bt, bx, by in path if t - 6.0 <= bt < t and 0 <= bx <= L]
        if not seen:
            continue
        seen_t, sx, sy = seen[-1]
        frame = min(frames, key=lambda f: abs(f['t'] - seen_t))
        team = [p for p in frame['players'] if p['team'] == scoring]
        holders = [sp for sp in spells if sp['team'] == scoring and t - 6.0 <= sp['end'] <= t]
        if holders and np.hypot(holders[-1]['end_xy'][0] - sx, holders[-1]['end_xy'][1] - sy) < 3:
            shooter = holders[-1]['player_id']
        elif team:
            shooter = min(team, key=lambda p: np.hypot(p['x'] - sx, p['y'] - sy))['player_id']
        else:
            continue
        events.append({'type': 'shot', 't': round(t - 0.4, 2), 'team': scoring, 'player_id': shooter,
                       'x': float(sx), 'y': float(sy), 'outcome': 'goal', 'speed_kmh': None})
        goal_times.add(round(t, 1))
    events.sort(key=lambda e: e['t'])
    # A possession change that was really a shot is reported once, as the shot.
    shots = {(round(e['t'], 2), e['player_id']) for e in events if e['type'] == 'shot'}
    return [e for e in events if not (e['type'] == 'pass' and (round(e['t'], 2), e['player_id']) in shots)]


def player_metrics(slots: list[Slot]) -> dict[str, dict[str, float]]:
    """Distance covered and top speed per player, from the smoothed observed track."""
    out = {}
    for s in slots:
        if len(s.path) < 3:
            continue
        path = np.array(s.path)
        dt = np.diff(path[:, 0])
        step = np.hypot(np.diff(path[:, 1]), np.diff(path[:, 2]))
        ok = (dt > 0) & (dt < 0.5)
        speed = step[ok] / dt[ok]
        top = float(np.percentile(speed, 95)) * 3.6 if len(speed) else 0.0
        out[s.player_id] = {'distance_m': round(float(step[ok].sum()), 1), 'top_speed_kmh': round(top, 1)}
    return out


def lineups_from(tracking_or_sheet: dict[str, Any]) -> dict[str, list[str]]:
    """The announced line-ups (team sheet): the only match information the pipeline is given."""
    teams = tracking_or_sheet.get('teams', tracking_or_sheet)
    return {t: sorted(p for p, team in teams.items() if team == t)[:11] for t in ('home', 'away')}


def frames_from(source: Path, stride: int):
    """Yield (index, BGR image) from a video file or a folder of rendered JPEG frames."""
    if source.is_dir():
        for i, path in enumerate(sorted((source / 'frames').glob('*.jpg'))):
            if i % stride == 0:
                yield i, cv2.imread(str(path))
        return
    capture = cv2.VideoCapture(str(source))
    i = 0
    while True:
        ok, image = capture.read()
        if not ok:
            break
        if i % stride == 0:
            yield i, image
        i += 1
    capture.release()


def observe_all(source: Path, start: float, fps: float = 25.0, stride: int = 2, limit: int | None = None,
                detector: PersonDetector | None = None, progress=print) -> list[dict[str, Any]]:
    detector = detector or PersonDetector()
    calibrator = Calibrator()
    out = []
    for n, (i, image) in enumerate(frames_from(source, stride)):
        if limit is not None and n >= limit:
            break
        out.append(observe(image, round(start + i / fps, 3), calibrator, detector))
        if progress and n % 50 == 0:
            progress(f'{n} frames')
    return out


def assemble(observations: list[dict[str, Any]], lineups: dict[str, list[str]], fps: float, stride: int) -> dict[str, Any]:
    assembler = Assembler(lineups, fps / stride, observations)
    for o in observations:
        assembler.step(o)
    return {'frames': assembler.frames, 'events': derive_events(assembler.frames),
            'players': player_metrics(assembler.slots), 'stride': stride,
            'start': observations[0]['t'] if observations else 0.0}


def run(source: Path, lineups: dict[str, list[str]], start: float, fps: float = 25.0, stride: int = 2,
        limit: int | None = None, detector: PersonDetector | None = None, progress=print) -> dict[str, Any]:
    """Process broadcast video that starts at match second `start`. Only the line-ups are given."""
    return assemble(observe_all(source, start, fps, stride, limit, detector, progress), lineups, fps, stride)
