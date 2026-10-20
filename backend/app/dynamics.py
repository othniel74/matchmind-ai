"""Measured game dynamics: control vs chaos, tempo and momentum.

Each state is a defined measurement over a rolling window, not a tactical judgement:
- turnovers per minute and passes per possession describe control vs chaos;
- on-ball events per minute describe tempo;
- a team's share of attacking-area on-ball events describes momentum.
Thresholds are percentiles of the simulator's own distribution (tuning seeds 1000-1199),
so "high" means high relative to this synthetic league, not to real football.
"""
from __future__ import annotations
from typing import Any
from .core import Event, ON_BALL_TYPES, TEAMS

WINDOW = 5            # minutes per dynamics window
MOMENTUM_WINDOW = 10  # minutes for momentum share
# Percentiles of 5-minute windows (10-minute for momentum) on tuning seeds 1000-1199.
CHAOS_TURNOVERS_PER_MIN = 3.2        # p80 of turnovers per minute
CONTROL_POSSESSION_SHARE = 0.65      # p85 of the leading team's share of passes
CONTROL_PASSES_PER_POSSESSION = 4.43 # p70 of the leading team's passes per possession
TEMPO_HIGH = 13.6                    # p80 of on-ball events per minute
TEMPO_LOW = 10.2                     # p20 of on-ball events per minute
MOMENTUM_SHARE = 0.84                # p80 of the leading team's share of attacking-area actions


def window_measures(events: list[Event], start: int, end: int) -> dict[str, Any]:
    """Raw measures for minutes [start, end)."""
    inside = [e for e in events if start <= e.minute < end]
    on_ball = [e for e in inside if e.event_type in ON_BALL_TYPES]
    minutes = max(end - start, 1)
    owners: dict[str, str] = {}
    passes: dict[str, int] = {}
    for e in inside:
        if not e.possession_id:
            continue
        owners.setdefault(e.possession_id, e.team_id)
        if e.event_type == 'pass' and e.team_id == owners[e.possession_id]:
            passes[e.possession_id] = passes.get(e.possession_id, 0) + 1
    by_team = {t: [p for p, owner in owners.items() if owner == t] for t in TEAMS}
    per_team_passes = {t: (sum(passes.get(p, 0) for p in ids) / len(ids) if ids else 0.0)
                       for t, ids in by_team.items()}
    pass_share = {t: sum(passes.get(p, 0) for p in by_team[t]) for t in TEAMS}
    total_passes = sum(pass_share.values())
    advanced = {t: sum(1 for e in on_ball if e.team_id == t and e.x >= 60) for t in TEAMS}
    return {
        'start': start, 'end': end,
        'turnovers_per_min': round(max(len(owners) - 1, 0) / minutes, 2),
        'passes_per_possession': {t: round(v, 2) for t, v in per_team_passes.items()},
        'pass_share': {t: round(pass_share[t] / total_passes, 3) if total_passes else 0.0 for t in TEAMS},
        'tempo_events_per_min': round(len(on_ball) / minutes, 2),
        'advanced_actions': advanced,
        'evidence_event_ids': [e.event_id for e in on_ball],
    }


def state_at(events: list[Event], minute: int) -> dict[str, Any] | None:
    """Control/chaos, tempo and momentum for the window ending at `minute` (causal)."""
    if minute < WINDOW:
        return None
    w = window_measures(events, minute - WINDOW, minute)
    leader = max(TEAMS, key=lambda t: w['pass_share'][t])
    if (w['pass_share'][leader] >= CONTROL_POSSESSION_SHARE
            and w['passes_per_possession'][leader] >= CONTROL_PASSES_PER_POSSESSION):
        control = {'state': 'control', 'team_id': leader}
    elif w['turnovers_per_min'] >= CHAOS_TURNOVERS_PER_MIN:
        control = {'state': 'chaos', 'team_id': None}
    else:
        control = {'state': 'balanced', 'team_id': None}
    tempo = ('high' if w['tempo_events_per_min'] >= TEMPO_HIGH
             else 'low' if w['tempo_events_per_min'] <= TEMPO_LOW else 'normal')
    momentum = None
    if minute >= MOMENTUM_WINDOW:
        m = window_measures(events, minute - MOMENTUM_WINDOW, minute)['advanced_actions']
        total = sum(m.values())
        if total:
            top = max(TEAMS, key=lambda t: m[t])
            share = m[top] / total
            momentum = {'team_id': top if share >= MOMENTUM_SHARE else None, 'share': round(share, 3),
                        'advanced_actions': m}
    return {'minute': minute, 'window': w, 'control': control, 'tempo': tempo, 'momentum': momentum,
            'definition': {'chaos_turnovers_per_min': CHAOS_TURNOVERS_PER_MIN,
                           'control_pass_share': CONTROL_POSSESSION_SHARE,
                           'control_passes_per_possession': CONTROL_PASSES_PER_POSSESSION,
                           'tempo_high': TEMPO_HIGH, 'tempo_low': TEMPO_LOW, 'momentum_share': MOMENTUM_SHARE}}


def timeline(events: list[Event], minute: int) -> list[dict[str, Any]]:
    """State every minute up to `minute`, for charts and change detection."""
    return [s for m in range(WINDOW, minute + 1) if (s := state_at(events, m))]
