"""Player-level intelligence: statistics, synthetic physical data, ratings, milestones and tags.

Statistics come from the event stream. Physical data (distance covered and top speed) is a
separate deterministic synthetic model: the event simulator has no tracking, so these values
are illustrative and labelled synthetic. Every on-screen tag cites the measurement behind it.
"""
from __future__ import annotations
from collections import defaultdict
from functools import lru_cache
from random import Random
from typing import Any
from .core import Event, ON_BALL_TYPES, SENDING_OFF, TEAMS, pass_difficulty
from .squads import PLAYERS

SPEED_TAG_KMH = 33.0              # top-speed alert threshold
DISTANCE_TAGS_KM = (5, 10)        # distance milestones
PASS_MILESTONES = (25, 50, 75)    # completed passes
SPRINT_KMH = 25.0                 # minutes with a top speed at or above this count as sprints
# Mean metres per minute and sprint probability per minute, by starting role.
_PHYSICAL = {'GK': (50, .02), 'RB': (108, .28), 'LB': (108, .28), 'RCB': (95, .15), 'LCB': (95, .15),
             'RCM': (118, .2), 'CDM': (115, .18), 'LCM': (118, .2), 'RW': (112, .3), 'LW': (112, .3),
             'ST': (104, .3), 'SUB': (114, .25)}


def on_pitch(events: list[Event]) -> dict[str, tuple[int, int]]:
    """Minutes [on, off) each player spent on the pitch, from substitutions and sending-offs."""
    spells = {pid: (0, 90) for pid, p in PLAYERS.items() if p.role != 'SUB'}
    for e in events:
        if e.event_type == 'substitution' and e.replacement_player_id:
            if e.player_id in spells:
                spells[e.player_id] = (spells[e.player_id][0], e.minute)
            spells[e.replacement_player_id] = (e.minute, 90)
        elif e.event_type == 'card' and e.outcome in SENDING_OFF and e.player_id in spells:
            spells[e.player_id] = (spells[e.player_id][0], e.minute)
    return spells


@lru_cache(maxsize=16)
def _physical(seed: int, spells: tuple) -> dict[str, list[tuple[float, float]]]:
    out = {}
    for pid, (start, end) in spells:
        mean, sprint = _PHYSICAL[PLAYERS[pid].role] if pid in PLAYERS else (100, .2)
        fresh = 1.05 if PLAYERS.get(pid) and PLAYERS[pid].role == 'SUB' else 1.0
        rows = []
        for minute in range(90):
            if not start <= minute < end:
                rows.append((0.0, 0.0))
                continue
            # Seed each player-minute on its own, so a later substitution or red card
            # can never change values already shown for earlier minutes.
            rng = Random(f'physical:{seed}:{pid}:{minute}')
            fatigue = 1 - .0012 * (minute - start)
            distance = max(0.0, rng.gauss(mean * fresh * fatigue, 12))
            top = rng.gauss(30.5, 2.2) if rng.random() < sprint else rng.gauss(22, 3)
            rows.append((round(distance, 1), round(max(8.0, min(36.0, top)), 1)))
        out[pid] = rows
    return out


def physical(events: list[Event], seed: int) -> dict[str, list[tuple[float, float]]]:
    """Per-player (metres, top km/h) for each minute 0-89; zero when off the pitch."""
    return _physical(seed, tuple(sorted(on_pitch(events).items())))


def player_stats(events: list[Event], seed: int, minute: int) -> dict[str, dict[str, Any]]:
    """Every squad player's statistics before `minute`, with the evidence behind them."""
    visible = [e for e in events if e.minute < minute]
    phys = physical(events, seed)
    spells = on_pitch(visible)
    stats: dict[str, dict[str, Any]] = {}
    for pid, p in PLAYERS.items():
        start, end = spells.get(pid, (None, None))
        played = max(0, min(end, minute) - start) if start is not None and start < minute else 0
        rows = phys[pid][:minute] if pid in phys else []
        stats[pid] = {'player_id': pid, 'team_id': p.team_id, 'name': p.name, 'shirt': p.shirt,
                      'position': p.position, 'minutes': played, 'touches': 0, 'passes': 0,
                      'completed_passes': 0, 'pass_accuracy_pct': 0.0, 'mean_pass_difficulty': 0.0,
                      'key_passes': 0, 'assists': 0, 'shots': 0, 'shots_on_target': 0, 'goals': 0,
                      'xg': 0.0, 'tackles_won': 0, 'recoveries': 0, 'fouls': 0, 'yellow_cards': 0,
                      'red_cards': 0, 'distance_km': round(sum(r[0] for r in rows) / 1000, 2),
                      'top_speed_kmh': max((r[1] for r in rows), default=0.0),
                      'sprints': sum(1 for r in rows if r[1] >= SPRINT_KMH),
                      'evidence_event_ids': []}
    difficulty: dict[str, list[float]] = defaultdict(list)
    last_pass: dict[str, Event] = {}
    for e in visible:
        s = stats.get(e.player_id)
        if s is None:
            continue
        if e.event_type in ON_BALL_TYPES:
            s['touches'] += 1
            s['evidence_event_ids'].append(e.event_id)
        if e.event_type == 'pass':
            s['passes'] += 1
            if e.outcome == 'success':
                s['completed_passes'] += 1
                difficulty[e.player_id].append(pass_difficulty(e))
                last_pass[e.possession_id] = e
        elif e.event_type == 'shot':
            s['shots'] += 1
            s['xg'] = round(s['xg'] + (e.xg or 0), 2)
            s['shots_on_target'] += e.outcome in {'goal', 'saved'}
            s['goals'] += e.outcome == 'goal'
            feeder = last_pass.get(e.possession_id)
            if feeder and feeder.recipient_player_id == e.player_id and feeder.team_id == e.team_id:
                stats[feeder.player_id]['key_passes'] += 1
                if e.outcome == 'goal':
                    stats[feeder.player_id]['assists'] += 1
        elif e.event_type == 'tackle':
            s['tackles_won'] += 1
        elif e.event_type == 'recovery':
            s['recoveries'] += 1
        elif e.event_type == 'foul':
            s['fouls'] += 1
        elif e.event_type == 'card':
            s['yellow_cards'] += e.outcome in {'yellow', 'second_yellow'}
            s['red_cards'] += e.outcome in SENDING_OFF
    for pid, s in stats.items():
        if s['passes']:
            s['pass_accuracy_pct'] = round(100 * s['completed_passes'] / s['passes'], 1)
        if difficulty[pid]:
            s['mean_pass_difficulty'] = round(sum(difficulty[pid]) / len(difficulty[pid]), 1)
        s['rating'] = rating(s)
    return stats


def rating(s: dict[str, Any]) -> float:
    """Transparent synthetic rating, 0-10: a 6.0 base plus weighted contributions."""
    if not s['minutes']:
        return 0.0
    score = (6.0 + 1.0 * s['goals'] + .6 * s['assists'] + .25 * s['key_passes'] + .3 * s['xg']
             + .15 * s['shots_on_target'] + .08 * s['tackles_won'] + .04 * s['recoveries']
             + .004 * s['completed_passes'] * (s['mean_pass_difficulty'] / 5 if s['mean_pass_difficulty'] else 1)
             - .25 * s['yellow_cards'] - 1.5 * s['red_cards'] - .05 * s['fouls'])
    if s['passes'] >= 10:
        score += (s['pass_accuracy_pct'] - 80) / 40
    return round(max(0.0, min(10.0, score)), 1)


def player_tags(events: list[Event], seed: int, minute: int) -> list[dict[str, Any]]:
    """Threshold-triggered physical tags (top speed, distance) and statistical milestones."""
    phys = physical(events, seed)
    tags = []
    for pid, rows in phys.items():
        fired_speed = False
        covered = 0.0
        next_distance = list(DISTANCE_TAGS_KM)
        for m, (metres, top) in enumerate(rows[:minute]):
            if top >= SPEED_TAG_KMH and not fired_speed:
                # Physical tags fire at the end of the minute whose data crossed the threshold.
                tags.append({'kind': 'top_speed', 'player_id': pid, 'minute': m, 'clock_seconds': m * 60 + 59, 'value': top,
                             'threshold': SPEED_TAG_KMH, 'unit': 'km/h', 'source': 'synthetic_physical'})
                fired_speed = True  # first time a player crosses the threshold
            covered += metres
            while next_distance and covered / 1000 >= next_distance[0]:
                tags.append({'kind': 'distance', 'player_id': pid, 'minute': m, 'clock_seconds': m * 60 + 59,
                             'value': next_distance[0],
                             'threshold': next_distance[0], 'unit': 'km', 'source': 'synthetic_physical'})
                next_distance.pop(0)
    completed: dict[str, int] = defaultdict(int)
    goals: dict[str, int] = defaultdict(int)
    for e in events:
        if e.minute >= minute or e.player_id not in PLAYERS:
            continue
        if e.event_type == 'pass' and e.outcome == 'success':
            completed[e.player_id] += 1
            if completed[e.player_id] in PASS_MILESTONES:
                tags.append({'kind': 'passes', 'player_id': e.player_id, 'minute': e.minute,
                             'clock_seconds': e.minute * 60 + e.second,
                             'value': completed[e.player_id], 'unit': 'completed passes',
                             'source': 'events', 'evidence_event_ids': [e.event_id]})
        elif e.event_type == 'shot' and e.outcome == 'goal':
            goals[e.player_id] += 1
            if goals[e.player_id] >= 2:
                tags.append({'kind': 'brace' if goals[e.player_id] == 2 else 'hat_trick', 'player_id': e.player_id,
                             'minute': e.minute, 'clock_seconds': e.minute * 60 + e.second,
                             'value': goals[e.player_id], 'unit': 'goals',
                             'source': 'events', 'evidence_event_ids': [e.event_id]})
    return sorted(tags, key=lambda t: (t['minute'], t['player_id'], t['kind']))
