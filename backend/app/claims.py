"""Typed, evidence-backed match claims with exact recomputation.

Each claim names a metric, a team (or both, for comparisons), a cutoff minute and a
value, plus the exact source events that produce the value and fixed EN/ES wording.
validate_claim recomputes everything from the event stream, so a claim with a changed
number, missing or future evidence, or reworded text is rejected. This covers counted
match facts; it is not a check of free-form language.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from .core import Event, SENDING_OFF, TEAMS, possession_seconds
from .languages import SUPPORTED, format_number, language as language_spec
from .squads import CLUBS


@dataclass(frozen=True)
class Metric:
    select: Callable[[Event], bool]
    # How the value is computed from the selected events; defaults to their count.
    value: Callable[[list[Event], list[Event], str], float] | None = None
    unit: str = ''


def _completion(selected: list[Event], visible: list[Event], team: str) -> float:
    return round(100 * sum(e.outcome == 'success' for e in selected) / len(selected), 1) if selected else 0.0


def _possession(selected: list[Event], visible: list[Event], team: str) -> float:
    held = possession_seconds(visible)
    total = sum(held.values())
    return round(100 * held[team] / total, 1) if total else 0.0


def _possession_starts(visible: list[Event]) -> list[Event]:
    """First event of every possession, both teams: a possession share depends on all of them."""
    seen, starts = set(), []
    for e in visible:
        if e.possession_id and e.possession_id not in seen:
            seen.add(e.possession_id)
            starts.append(e)
    return starts


METRICS: dict[str, Metric] = {
    'goals': Metric(lambda e: e.event_type == 'shot' and e.outcome == 'goal'),
    'shots': Metric(lambda e: e.event_type == 'shot'),
    'shots_on_target': Metric(lambda e: e.event_type == 'shot' and e.outcome in {'goal', 'saved'}),
    'xg': Metric(lambda e: e.event_type == 'shot',
                 lambda selected, visible, team: round(sum(e.xg or 0 for e in selected), 2)),
    'pass_completion': Metric(lambda e: e.event_type == 'pass', _completion, '%'),
    'possession': Metric(lambda e: False, _possession, '%'),
    'corners': Metric(lambda e: e.event_type == 'pass' and e.set_piece == 'corner'),
    'fouls': Metric(lambda e: e.event_type == 'foul'),
    'yellow_cards': Metric(lambda e: e.event_type == 'card' and e.outcome in {'yellow', 'second_yellow'}),
    'red_cards': Metric(lambda e: e.event_type == 'card' and e.outcome in SENDING_OFF),
    'substitutions': Metric(lambda e: e.event_type == 'substitution'),
}


def measure(events: list[Event], metric: str, team: str, minute: int) -> tuple[float, list[str]]:
    """Value and supporting event IDs for one team using only events before `minute`."""
    spec = METRICS[metric]
    visible = [e for e in events if e.minute < minute]
    if metric == 'possession':
        selected = _possession_starts(visible)
    else:
        selected = [e for e in visible if e.team_id == team and spec.select(e)]
    value = spec.value(selected, visible, team) if spec.value else len(selected)
    return value, [e.event_id for e in selected]


def statement(kind: str, metric: str, minute: int, values: dict[str, float], code: str) -> str:
    spec = language_spec(code)
    unit = METRICS[metric].unit
    label = spec.metrics[metric]
    names = {'home': CLUBS['home'].short, 'away': CLUBS['away'].short}
    if kind == 'score':
        return spec.claims['score'].format(home=names['home'], away=names['away'], h=values['home'],
                                           a=values['away'], sep=spec.score, m=minute)
    if kind == 'compare':
        return spec.claims['compare'].format(m=minute, label=label, home=names['home'], away=names['away'],
                                             h=format_number(values['home'], unit, code),
                                             a=format_number(values['away'], unit, code))
    team = next(iter(values))
    joiner = spec.percent_joiner if unit == '%' else ' '
    return spec.claims['team_value'].format(team=names[team], value=format_number(values[team], unit, code),
                                            joiner=joiner, label=label, m=minute)


def make_claim(events: list[Event], kind: str, metric: str, minute: int, team: str | None = None) -> dict[str, Any]:
    teams = TEAMS if kind in {'score', 'compare'} else (team,)
    values, evidence = {}, []
    for side in teams:
        value, ids = measure(events, 'goals' if kind == 'score' else metric, side, minute)
        values[side] = value
        evidence.extend(ids)
    metric = 'goals' if kind == 'score' else metric
    claim_id = f"claim:{kind}:{metric}:{team or 'both'}:{minute}"
    return {'claim_id': claim_id, 'kind': kind, 'metric': metric, 'team_id': team, 'minute': minute,
            'values': values, 'evidence_event_ids': sorted(set(evidence)),
            'statements': {code: statement(kind, metric, minute, values, code) for code in SUPPORTED}}


def match_claims(events: list[Event], minute: int) -> list[dict[str, Any]]:
    """Every supported claim at a cutoff: the score, per-team facts and head-to-head comparisons."""
    claims = [make_claim(events, 'score', 'goals', minute)]
    for metric in METRICS:
        if metric == 'goals':
            continue
        claims.append(make_claim(events, 'compare', metric, minute))
        for team in TEAMS:
            claims.append(make_claim(events, 'team_value', metric, minute, team))
    return claims


def validate_claim(claim: dict[str, Any], events: list[Event]) -> tuple[bool, str]:
    """Recompute a claim from source events; return (valid, reason)."""
    try:
        kind, metric, minute, team = claim['kind'], claim['metric'], claim['minute'], claim.get('team_id')
        if kind not in {'score', 'compare', 'team_value'} or metric not in METRICS:
            return False, 'unsupported_claim'
        if kind == 'score' and metric != 'goals':
            return False, 'unsupported_claim'
        if (kind == 'team_value') != (team in TEAMS) or not 1 <= int(minute) <= 90:
            return False, 'invalid_scope'
        expected = make_claim(events, kind, metric, minute, team)
    except (KeyError, TypeError, ValueError):
        return False, 'malformed_claim'
    by_id = {e.event_id: e for e in events}
    if any(i not in by_id or by_id[i].minute >= minute for i in claim.get('evidence_event_ids', [])):
        return False, 'evidence_outside_scope'
    if claim.get('values') != expected['values']:
        return False, 'value_mismatch'
    if sorted(claim.get('evidence_event_ids', [])) != expected['evidence_event_ids']:
        return False, 'evidence_mismatch'
    if claim.get('statements') != expected['statements'] or claim.get('claim_id') != expected['claim_id']:
        return False, 'statement_mismatch'
    return True, 'valid'
