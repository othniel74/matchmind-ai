"""Personalized experience: the same verified intelligence shaped for one viewer.

A profile combines audience mode, language, favourite club, favourite players, a player
to follow and a single metric to track. Personalization changes selection, emphasis and
framing, never the facts: every item still comes from verified moments and claims.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from .claims import METRICS, make_claim, measure
from .core import Event, TEAMS, statistics
from .dynamics import state_at
from .languages import language as language_spec
from .moment_text import MOMENT_TEXT
from .moments import detect_moments, render
from .players import physical, player_stats
from .squads import CLUBS, PLAYERS, name

AUDIENCES = ('fan', 'analyst', 'broadcast')
# Moment kinds each audience sees by default; favourites can add more (see relevance).
AUDIENCE_KINDS = {
    'fan': {'goal', 'hat_trick', 'brace', 'red_card', 'big_chance', 'momentum', 'substitution', 'yellow_card',
            'top_speed'},
    'analyst': set(),  # empty means every kind
    'broadcast': {'goal', 'hat_trick', 'brace', 'red_card', 'big_chance', 'momentum', 'control', 'chaos',
                  'substitution', 'activity', 'top_speed', 'connector'},
}


@dataclass(frozen=True)
class Profile:
    audience: str = 'fan'
    language: str = 'en'
    club: str | None = None                  # 'home' or 'away'
    players: tuple[str, ...] = field(default_factory=tuple)
    focus_player: str | None = None
    metric: str | None = None

    def validate(self) -> 'Profile':
        language_spec(self.language)
        if self.audience not in AUDIENCES:
            raise ValueError('audience must be fan, analyst or broadcast')
        if self.club not in (None, *TEAMS):
            raise ValueError('club must be home or away')
        unknown = [p for p in (*self.players, *( [self.focus_player] if self.focus_player else [])) if p not in PLAYERS]
        if unknown:
            raise ValueError(f'Unknown players: {", ".join(unknown)}')
        if self.metric is not None and self.metric not in METRICS:
            raise ValueError(f'metric must be one of {", ".join(METRICS)}')
        return self


@lru_cache(maxsize=64)
def _moments_cached(key: tuple, seed: int, minute: int, events: tuple) -> tuple:
    return tuple(detect_moments(list(events), seed, minute))


def moments_for(events: list[Event], seed: int, minute: int, state_key: Any = None) -> list[dict[str, Any]]:
    """Moments are recomputed only when the source state or the minute changes."""
    return list(_moments_cached((state_key, len(events)), seed, minute, tuple(events)))


def relevance(moment: dict[str, Any], profile: Profile) -> tuple[bool, int, dict[str, bool]]:
    favourite_player = bool(set(moment['player_ids']) & ({*profile.players} | ({profile.focus_player} - {None})))
    favourite_club = profile.club is not None and moment['team_id'] == profile.club
    allowed = AUDIENCE_KINDS[profile.audience]
    shown = not allowed or moment['kind'] in allowed or favourite_player
    if profile.focus_player and not favourite_player and moment['kind'] not in {'goal', 'red_card', 'hat_trick'}:
        shown = False  # player-focus mode: follow one player, keep only match-changing events
    score = moment['priority'] + 4 * favourite_player + (2 if favourite_club and profile.audience == 'fan' else 0)
    return shown, score, {'favourite_club': favourite_club, 'favourite_player': favourite_player}


def personalized_moments(moments: list[dict[str, Any]], profile: Profile, limit: int = 30) -> list[dict[str, Any]]:
    items = []
    for m in moments:
        shown, score, flags = relevance(m, profile)
        if shown:
            items.append({**m, **render(m, profile.language), **flags, 'relevance': score,
                          'player_names': [name(p) for p in m['player_ids']]})
    # Newest first, so the feed reads like a live ticker; relevance breaks ties.
    return sorted(items, key=lambda x: (-x['clock_seconds'], -x['relevance']))[:limit]


def focus_card(events: list[Event], seed: int, minute: int, player_id: str,
               stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    timeline = []
    for e in events:
        if e.minute >= minute:
            break
        involved = e.player_id == player_id or e.recipient_player_id == player_id or e.replacement_player_id == player_id
        if involved and e.event_type in {'shot', 'tackle', 'recovery', 'foul', 'card', 'substitution'} \
                or (e.player_id == player_id and e.event_type == 'pass' and e.outcome == 'success'
                    and (e.end_x or 0) >= 70):
            timeline.append({'clock_seconds': e.minute * 60 + e.second, 'event_id': e.event_id,
                             'event_type': e.event_type, 'outcome': e.outcome, 'xg': e.xg,
                             'speed_kmh': e.speed_kmh, 'x': e.x, 'y': e.y})
    rows = physical(events, seed).get(player_id, [])[:minute]
    covered, series = 0.0, []
    for m, (metres, top) in enumerate(rows):
        covered += metres
        if m % 5 == 4:
            series.append({'minute': m + 1, 'distance_km': round(covered / 1000, 2), 'top_speed_kmh': top})
    return {'player': stats[player_id], 'timeline': timeline[-40:], 'physical': series,
            'physical_source': 'synthetic_physical', 'network_role': network_role(events, minute, player_id)}


def network_role(events: list[Event], minute: int, player_id: str) -> dict[str, Any]:
    """The player's place in their team's pass network: whole match so far and last 15 minutes."""
    from .graph.analytics import passing_graph, roles
    team = PLAYERS[player_id].team_id
    visible = [e for e in events if e.minute < minute]
    out = {}
    for label, start in (('match', 0), ('last_15', max(0, minute - 15))):
        net = passing_graph(visible, team, start, minute)
        window = roles(net, team, start, minute, name)
        entry = next((p for p in window['players'] if p['player_id'] == player_id), None)
        partners: dict[str, int] = {}
        if player_id in net:
            for u, v, d in [*net.out_edges(player_id, data=True), *net.in_edges(player_id, data=True)]:
                other = v if u == player_id else u
                partners[other] = partners.get(other, 0) + d['weight']
        out[label] = {'window': window['window'], 'completed_passes': window['completed_passes'],
                      'pass_share': entry['pass_share'] if entry else 0.0,
                      'betweenness': entry['betweenness'] if entry else 0.0,
                      'pagerank': entry['pagerank'] if entry else 0.0,
                      'pagerank_rank': next((i + 1 for i, p in enumerate(window['players'])
                                             if p['player_id'] == player_id), None),
                      'is_hub': window['hub'] == player_id, 'is_connector': window['connector'] == player_id,
                      'top_partners': [{'player_id': p, 'name': name(p), 'passes': n} for p, n in
                                       sorted(partners.items(), key=lambda x: (-x[1], x[0]))[:3]]}
    return out


def metric_tracker(events: list[Event], minute: int, metric: str, code: str) -> dict[str, Any]:
    series = [{'minute': m, **{t: measure(events, metric, t, m)[0] for t in TEAMS}}
              for m in range(5, minute + 1, 5)] if minute >= 5 else []
    claim = make_claim(events, 'compare', metric, max(minute, 1))
    return {'metric': metric, 'label': language_spec(code).metrics[metric], 'series': series,
            'current': claim['values'], 'statement': claim['statements'][code], 'claim_id': claim['claim_id']}


def experience(events: list[Event], seed: int, minute: int, profile: Profile, state_key: Any = None) -> dict[str, Any]:
    profile.validate()
    visible = [e for e in events if e.minute < minute]
    stats = player_stats(events, seed, minute)
    text = MOMENT_TEXT[profile.language]
    state = state_at(visible, minute)
    result = {
        'profile': {**vars(profile), 'players': list(profile.players)},
        'clubs': {t: {**vars(c), 'favourite': profile.club == t,
                      'label': text['your_club'] if profile.club == t else None} for t, c in CLUBS.items()},
        'statistics': statistics(visible),
        'moments': personalized_moments(moments_for(events, seed, minute, state_key), profile),
        'dynamics': state,
        'favourite_players': [{**stats[p], 'label': text['your_player']} for p in profile.players],
        'direction': language_spec(profile.language).direction,
    }
    if profile.focus_player:
        result['focus'] = focus_card(events, seed, minute, profile.focus_player, stats)
    if profile.metric:
        result['metric'] = metric_tracker(visible, minute, profile.metric, profile.language)
    return result
