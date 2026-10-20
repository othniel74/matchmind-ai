"""Key moments: what happened, why it matters, and how to show it, from verified data.

Every moment is causal (uses only events before its own clock), cites evidence, and is
rendered from fixed per-language templates, so numbers and names are never generated.
"""
from __future__ import annotations
from typing import Any
from .core import Event, SENDING_OFF, TEAMS, detect_insights
from .dynamics import state_at
from .languages import format_number, language as language_spec
from .moment_text import MOMENT_TEXT
from .graph.analytics import passing_graph, roles
from .players import player_tags
from .squads import CLUBS, name

BIG_CHANCE_XG = 0.3
# A team's key connector is the player with the highest betweenness on its pass network over
# the last 15 minutes; a change is a moment once the network has enough passes to be stable.
CONNECTOR_WINDOW = 15
CONNECTOR_MIN_PASSES = 20
CONNECTOR_MIN_BETWEENNESS = 0.25
CONNECTOR_MIN_SHARE = 0.25  # involved in at least a quarter of the team's completed passes
DYNAMICS_DEBOUNCE = 8  # minutes between two dynamics moments of the same kind
PRIORITY = {'goal': 10, 'hat_trick': 10, 'red_card': 9, 'brace': 9, 'big_chance': 7, 'activity': 6,
            'momentum': 6, 'connector': 5, 'control': 5, 'chaos': 5, 'tempo_high': 4, 'tempo_low': 4, 'substitution': 4,
            'yellow_card': 3, 'top_speed': 3, 'passes': 3, 'distance': 2}
DURATION_MS = {'goal': 12000, 'red_card': 10000, 'hat_trick': 12000, 'brace': 10000}


def _clock(e: Event) -> int:
    return e.minute * 60 + e.second


def _score(events: list[Event]) -> dict[str, int]:
    return {t: sum(e.team_id == t and e.event_type == 'shot' and e.outcome == 'goal' for e in events) for t in TEAMS}


def detect_moments(events: list[Event], seed: int, minute: int) -> list[dict[str, Any]]:
    visible = [e for e in events if e.minute < minute]
    moments: list[dict[str, Any]] = []
    score = {t: 0 for t in TEAMS}
    players_on = {t: 11 for t in TEAMS}
    last_pass: dict[str, Event] = {}

    def add(kind, clock, team, player_ids, facts, evidence, why=None):
        moments.append({'id': f'{kind}:{clock}:{"-".join(player_ids) or team or "match"}', 'kind': kind,
                        'clock_seconds': clock, 'minute': clock // 60, 'team_id': team, 'player_ids': player_ids,
                        'facts': facts, 'why': why, 'evidence_event_ids': evidence,
                        'priority': PRIORITY[kind], 'duration_ms': DURATION_MS.get(kind, 8000)})

    for e in visible:
        if e.event_type == 'pass' and e.outcome == 'success':
            last_pass[e.possession_id] = e
        if e.event_type == 'shot':
            if e.outcome == 'goal':
                before = dict(score)
                score[e.team_id] += 1
                other = 'away' if e.team_id == 'home' else 'home'
                if before == {'home': 0, 'away': 0}:
                    why = 'opener'
                elif score[e.team_id] == score[other]:
                    why = 'equaliser'
                elif before[e.team_id] == before[other]:
                    why = 'go_ahead'
                elif before[e.team_id] > before[other]:
                    why = 'extends'
                else:
                    why = 'pulls_back'
                feeder = last_pass.get(e.possession_id)
                assister = feeder.player_id if (feeder and feeder.recipient_player_id == e.player_id
                                                 and feeder.team_id == e.team_id) else None
                add('goal', _clock(e), e.team_id, [e.player_id] + ([assister] if assister else []),
                    {'home': score['home'], 'away': score['away'], 'xg': e.xg, 'assister': assister,
                     'speed_kmh': e.speed_kmh}, [e.event_id] + ([feeder.event_id] if assister else []), why)
            elif (e.xg or 0) >= BIG_CHANCE_XG:
                add('big_chance', _clock(e), e.team_id, [e.player_id], {'xg': e.xg, 'outcome': e.outcome},
                    [e.event_id])
        elif e.event_type == 'card':
            if e.outcome in SENDING_OFF:
                players_on[e.team_id] -= 1
                add('red_card', _clock(e), e.team_id, [e.player_id], {'players_left': players_on[e.team_id]},
                    [e.event_id], 'down_to')
            else:
                add('yellow_card', _clock(e), e.team_id, [e.player_id], {}, [e.event_id])
        elif e.event_type == 'substitution':
            add('substitution', _clock(e), e.team_id, [e.replacement_player_id, e.player_id], {}, [e.event_id])

    for tag in player_tags(events, seed, minute):
        team = tag['player_id'].split('-')[0]
        add(tag['kind'], tag['clock_seconds'], team, [tag['player_id']],
            {'value': tag['value'], 'unit': tag['unit'], 'source': tag['source']}, tag.get('evidence_event_ids', []))

    for m in range(20, minute + 1):
        for insight in detect_insights(visible, m):
            add('activity', m * 60, insight['team_id'], [],
                {'previous': insight['previous_count'], 'current': insight['current_count'],
                 'interpretation': insight['interpretation']}, insight['evidence_event_ids'])

    connectors: dict[str, str] = {}
    for m in range(30, minute + 1, 10):
        for team in ('home', 'away'):
            net = passing_graph(visible, team, m - CONNECTOR_WINDOW, m)
            window = roles(net, team, m - CONNECTOR_WINDOW, m)
            if window['completed_passes'] < CONNECTOR_MIN_PASSES:
                continue
            key = next(p for p in window['players'] if p['player_id'] == window['connector'])
            if (key['betweenness'] >= CONNECTOR_MIN_BETWEENNESS and key['pass_share'] >= CONNECTOR_MIN_SHARE
                    and connectors.get(team) != key['player_id']):
                # Evidence: every completed pass the connector made or received in the window.
                evidence = sorted(i for u, v, d in net.edges(data=True) if key['player_id'] in (u, v)
                                  for i in d['event_ids'])
                add('connector', m * 60, team, [key['player_id']],
                    {'share': key['pass_share'], 'betweenness': key['betweenness'],
                     'passes': window['completed_passes'], 'window': [m - CONNECTOR_WINDOW, m]}, evidence)
            connectors[team] = key['player_id']

    previous: dict[str, Any] = {}
    last_fired: dict[str, int] = {}
    for m in range(5, minute + 1):
        state = state_at(visible, m)
        if state is None:
            continue
        current = {'control': (state['control']['state'], state['control']['team_id']),
                   'tempo': state['tempo'], 'momentum': (state['momentum'] or {}).get('team_id')}
        w = state['window']
        candidates = []
        if current['control'] != previous.get('control') and current['control'][0] in ('control', 'chaos'):
            kind, team = current['control']
            facts = ({'share': w['pass_share'][team], 'ppp': w['passes_per_possession'][team]} if kind == 'control'
                     else {'turnovers': w['turnovers_per_min']})
            candidates.append((kind, team, facts))
        if current['tempo'] != previous.get('tempo') and current['tempo'] in ('high', 'low'):
            candidates.append((f"tempo_{current['tempo']}", None, {'tempo': w['tempo_events_per_min']}))
        if current['momentum'] and current['momentum'] != previous.get('momentum'):
            candidates.append(('momentum', current['momentum'], {'share': state['momentum']['share']}))
        for kind, team, facts in candidates:
            if m - last_fired.get(kind, -99) >= DYNAMICS_DEBOUNCE:
                add(kind, m * 60, team, [], {**facts, 'definition': state['definition']}, w['evidence_event_ids'])
                last_fired[kind] = m
        previous = current
    return sorted(moments, key=lambda x: (x['clock_seconds'], -x['priority'], x['id']))


def render(moment: dict[str, Any], code: str) -> dict[str, str]:
    """Headline and body for one moment in one language, from fixed templates."""
    text = MOMENT_TEXT[code]
    spec = language_spec(code)
    f = moment['facts']
    club = CLUBS[moment['team_id']].short if moment['team_id'] else ''
    player = name(moment['player_ids'][0]) if moment['player_ids'] else ''
    num = lambda value, unit='': format_number(value, unit, code)
    kind = moment['kind']
    body = ''
    if kind == 'goal':
        score = f"{CLUBS['home'].short} {f['home']}{spec.score}{f['away']} {CLUBS['away'].short}"
        headline = text['goal'].format(player=player, club=club)
        lines = [text[f"why_{moment['why']}"].format(score=score, club=club)]
        if f.get('assister'):
            lines.append(text['assist'].format(assister=name(f['assister'])))
        if f.get('xg') is not None:
            lines.append(text['xg_line'].format(xg=num(round(f['xg'], 2))))
        body = ' · '.join(lines)
    elif kind == 'big_chance':
        headline = text['big_chance'].format(club=club)
        body = text['big_chance_body'].format(player=player, xg=num(round(f['xg'], 2)))
    elif kind == 'red_card':
        headline = text['red_card'].format(player=player)
        body = text['red_card_why'].format(club=club, n=f['players_left'])
    elif kind == 'yellow_card':
        headline = text['yellow_card'].format(player=player)
    elif kind == 'substitution':
        headline = text['substitution'].format(club=club, on=player, off=name(moment['player_ids'][1]))
    elif kind in ('top_speed', 'distance'):
        headline = text[kind].format(player=player, value=num(f['value']))
        body = text['synthetic_note']
    elif kind in ('passes', 'brace', 'hat_trick'):
        headline = text[kind].format(player=player, value=f['value'])
    elif kind == 'control':
        headline = text['control'].format(club=club)
        body = text['control_body'].format(share=num(round(100 * f['share'], 1), '%'), ppp=num(f['ppp']))
    elif kind == 'chaos':
        headline, body = text['chaos'], text['chaos_body'].format(turnovers=num(f['turnovers']))
    elif kind in ('tempo_high', 'tempo_low'):
        headline, body = text[kind], text['tempo_body'].format(tempo=num(f['tempo']))
    elif kind == 'connector':
        headline = text['connector'].format(player=player, club=club)
        body = text['connector_body'].format(share=num(round(100 * f['share'], 1), '%'), club=club)
    elif kind == 'momentum':
        headline = text['momentum'].format(club=club)
        body = text['momentum_body'].format(share=num(round(100 * f['share'], 1), '%'))
    elif kind == 'activity':
        team = moment['team_id']
        values = {'prev': f['previous'], 'curr': f['current'], 'club': CLUBS[team].short}
        headline = spec.narrative['headline'].format(**values)
        body = spec.narrative['broadcast'].format(**values)
    else:
        raise ValueError(f'Unknown moment kind: {kind}')
    return {'headline': headline, 'body': body, 'direction': spec.direction, 'language': code}
