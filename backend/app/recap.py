"""Automated match recaps (half-time, full-time or so far), built only from verified facts.

Every number in a recap is a claim from claims.py and is validated before it is returned;
moments and player lines come from the same verified sources as the live product.
"""
from __future__ import annotations
from typing import Any
from .claims import make_claim, validate_claim
from .core import Event, TEAMS
from .dynamics import timeline
from .experience import Profile, moments_for
from .languages import format_number, language as language_spec
from .moment_text import MOMENT_TEXT
from .moments import render
from .players import player_stats
from .squads import CLUBS, name

RECAP_METRICS = ('shots', 'shots_on_target', 'xg', 'possession', 'pass_completion', 'corners', 'fouls', 'yellow_cards')


def build_recap(events: list[Event], seed: int, minute: int, profile: Profile, state_key: Any = None) -> dict[str, Any]:
    profile.validate()
    code = profile.language
    text = MOMENT_TEXT[code]
    kind = 'full' if minute >= 90 else 'half' if minute == 45 else 'live'
    claims = [make_claim(events, 'score', 'goals', minute)] + \
             [make_claim(events, 'compare', metric, minute) for metric in RECAP_METRICS]
    for claim in claims:
        valid, reason = validate_claim(claim, events)
        if not valid:
            raise RuntimeError(f'Recap claim failed validation: {claim["claim_id"]} ({reason})')
    moments = moments_for(events, seed, minute, state_key)
    goals = [m for m in moments if m['kind'] == 'goal']
    scorers = [{'clock_seconds': g['clock_seconds'], 'minute': g['minute'] + 1, 'player_id': g['player_ids'][0],
                'player': name(g['player_ids'][0]), 'team_id': g['team_id'], **render(g, code)} for g in goals]
    key = sorted((m for m in moments if m['kind'] not in {'goal', 'top_speed', 'distance', 'passes'}),
                 key=lambda m: (-m['priority'], m['clock_seconds']))[:5]
    key_moments = [{'clock_seconds': m['clock_seconds'], 'kind': m['kind'], **render(m, code)}
                   for m in sorted(key, key=lambda m: m['clock_seconds'])]

    states = timeline([e for e in events if e.minute < minute], minute)
    control = {t: sum(1 for s in states if s['control'] == {'state': 'control', 'team_id': t}) for t in TEAMS}
    chaos = sum(1 for s in states if s['control']['state'] == 'chaos')
    leader = max(TEAMS, key=lambda t: control[t])
    # Built from parts so empty spells are left out (no "0 minutes") and no plurals are needed.
    parts = ([text['flow_control'].format(club=CLUBS[leader].short, a=control[leader])] if control[leader] else []) + \
            ([text['flow_chaos'].format(b=chaos)] if chaos else [])
    separator = '، ' if code == 'ar' else '; '
    colon = ' : ' if code == 'fr' else ': '  # French typography spaces the colon
    flow = f"{text['flow_prefix']}{colon}{separator.join(parts) if parts else text['flow_none']}"

    stats = player_stats(events, seed, minute)
    best = max((s for s in stats.values() if s['minutes']), key=lambda s: (s['rating'], s['goals']))
    player_line = text['recap_player' if kind == 'full' else 'recap_player_half'].format(
        player=best['name'], club=CLUBS[best['team_id']].short, value=format_number(best['rating'], '', code))
    followed = [p for p in dict.fromkeys([*profile.players, *([profile.focus_player] if profile.focus_player else [])])]
    focus_lines = [text['recap_focus'].format(player=stats[p]['name'], goals=stats[p]['goals'],
                                              passes=stats[p]['completed_passes'],
                                              km=format_number(stats[p]['distance_km'], '', code)) for p in followed]
    title = text[f'recap_{kind}']
    sections = {
        'score': claims[0]['statements'][code],
        'scorers': scorers,
        'statistics': [c['statements'][code] for c in claims[1:]],
        'key_moments': key_moments,
        'flow': flow,
        'player_of_match': {'player_id': best['player_id'], 'rating': best['rating'], 'text': player_line},
        'followed_players': focus_lines,
    }
    lines = [f'{title} — {sections["score"]}']
    lines += [f'{s["minute"]}′ {s["headline"]}' for s in scorers]
    lines += [text['recap_stats'] + ':'] + [f'• {s}' for s in sections['statistics']]
    lines += [flow, player_line, *focus_lines]
    return {'kind': kind, 'minute': minute, 'title': title, 'language': code,
            'direction': language_spec(code).direction, 'sections': sections,
            'claim_ids': [c['claim_id'] for c in claims], 'claims': claims, 'text': '\n'.join(lines),
            'engine': 'deterministic_verified'}


FACT_METRICS = ('shots', 'shots_on_target', 'xg', 'possession', 'corners')


def recap_facts(events: list[Event], minute: int) -> dict[str, Any]:
    """Verified facts an agent may restate in a recap: result, scorers and statistic leaders."""
    from .claims import measure
    visible = [e for e in events if e.minute < minute]
    goals = {t: sum(e.team_id == t and e.event_type == 'shot' and e.outcome == 'goal' for e in visible) for t in TEAMS}
    final = minute >= 90
    if goals['home'] == goals['away']:
        result = {t: 'drew' if final else 'level' for t in TEAMS}
    else:
        leader = max(TEAMS, key=lambda t: goals[t])
        trailer = 'away' if leader == 'home' else 'home'
        result = {leader: 'won' if final else 'leads', trailer: 'lost' if final else 'trails'}
    scorers: dict[str, dict[str, Any]] = {}
    for e in visible:
        if e.event_type == 'shot' and e.outcome == 'goal':
            entry = scorers.setdefault(e.player_id, {'player': name(e.player_id), 'team_id': e.team_id, 'goals': 0})
            entry['goals'] += 1
    leaders = {}
    for metric in FACT_METRICS:
        values = {t: measure(events, metric, t, minute)[0] for t in TEAMS}
        leaders[metric] = None if values['home'] == values['away'] else max(TEAMS, key=lambda t: values[t])
    return {'minute': minute, 'final': final, 'goals': goals, 'result': result,
            'scorers': list(scorers.values()), 'leaders': leaders}
