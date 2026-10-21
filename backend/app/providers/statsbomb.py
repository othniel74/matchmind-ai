"""StatsBomb event data (open-data JSON format) -> MatchMind events.

StatsBomb publishes free open data for research under its own licence; MatchMind does not
include any. Point this adapter at a downloaded `events/<match_id>.json` (and optionally the
matching `lineups/<match_id>.json`) to run MatchMind's validation, claims and analytics on it:

    python -m app.providers.statsbomb events.json [--lineups lineups.json] [--home-team-id 779]

Mapping:
- teams: the home team (given, or the first team in the Starting XI events) is `home`;
- players: `<team>-<shirt number>` from the lineups or the Starting XI tactics, with the
  provider's names kept in the returned roster;
- coordinates: StatsBomb's 120 x 80 pitch, each team attacking left to right, becomes MatchMind's
  team-relative 0-100 scale;
- clock: the provider's minute and second with the `period`, so stoppage and extra time stay valid;
- types: Pass, Shot, Duel (tackle), Ball Recovery, Interception, Foul Committed, cards (from fouls
  and Bad Behaviour) and Substitution. Other types (carries, pressures, receipts, clearances...)
  are counted in the report as not represented by the current event contract.
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..core import Event, StreamValidator

SHOT_OUTCOMES = {'Goal': 'goal', 'Saved': 'saved', 'Saved To Post': 'saved', 'Saved Off Target': 'saved',
                 'Blocked': 'blocked', 'Off T': 'missed', 'Wayward': 'missed', 'Post': 'missed'}
PASS_SET_PIECES = {'Corner': 'corner', 'Free Kick': 'free_kick', 'Throw-in': 'throw_in', 'Goal Kick': 'goal_kick',
                   'Kick Off': 'kick_off'}
SHOT_SET_PIECES = {'Penalty': 'penalty', 'Free Kick': 'free_kick', 'Corner': 'corner'}
CARDS = {'Yellow Card': 'yellow', 'Second Yellow': 'second_yellow', 'Red Card': 'red'}


def _xy(location: list[float] | None) -> tuple[float, float]:
    if not location:
        return 50.0, 50.0
    x, y = location[0], location[1]
    return round(min(max(x / 120 * 100, 0.0), 100.0), 1), round(min(max(y / 80 * 100, 0.0), 100.0), 1)


def roster(events: list[dict], lineups: list[dict] | None, home_team_id: int | None) -> tuple[dict[int, str], dict[int, str], dict[str, dict]]:
    """Team id -> 'home'/'away', provider player id -> MatchMind player id, and the roster."""
    starting = [e for e in events if e['type']['name'] == 'Starting XI']
    team_ids = [e['team']['id'] for e in starting] or sorted({e['team']['id'] for e in events if 'team' in e})
    home = home_team_id if home_team_id in team_ids else team_ids[0]
    side = {tid: 'home' if tid == home else 'away' for tid in team_ids}
    players: dict[int, str] = {}
    names: dict[str, dict] = {}

    def add(team_id: int, player: dict, number: int | None) -> None:
        if player['id'] in players or team_id not in side:
            return
        shirt = number if number is not None else 90 + len([p for p in players.values() if p.startswith(side[team_id])])
        pid = f'{side[team_id]}-{shirt:02d}'
        players[player['id']] = pid
        names[pid] = {'name': player.get('name') or player.get('player_name'), 'team_id': side[team_id],
                      'provider_id': player['id'], 'shirt': shirt}

    for team in lineups or []:
        for p in team.get('lineup', []):
            add(team['team_id'], {'id': p['player_id'], 'name': p.get('player_name')}, p.get('jersey_number'))
    for e in starting:
        for p in e.get('tactics', {}).get('lineup', []):
            add(e['team']['id'], p['player'], p.get('jersey_number'))
    for e in events:  # anyone else who appears (substitutes without a lineup file)
        if 'player' in e and 'team' in e:
            add(e['team']['id'], e['player'], None)
        replacement = e.get('substitution', {}).get('replacement')
        if replacement and 'team' in e:
            add(e['team']['id'], replacement, None)
    return side, players, names


def adapt(events: list[dict], lineups: list[dict] | None = None, home_team_id: int | None = None,
          match_id: str | None = None) -> dict[str, Any]:
    """Convert and validate. Returns accepted events, the roster and a report of everything else."""
    side, players, names = roster(events, lineups, home_team_id)
    match_id = match_id or f"statsbomb:{events[0].get('match_id', 'match') if events else 'empty'}"
    validator = StreamValidator()
    accepted: list[Event] = []
    rejected: list[dict] = []
    unsupported: Counter = Counter()
    ordered = sorted(events, key=lambda e: (e['period'], e['minute'], e['second'], e['index']))
    for e in ordered:
        kind = e['type']['name']
        if e['period'] == 5 or 'team' not in e or e['team']['id'] not in side:
            unsupported['penalty shoot-out' if e['period'] == 5 else kind] += 1
            continue
        team = side[e['team']['id']]
        player = players.get(e.get('player', {}).get('id'))
        x, y = _xy(e.get('location'))
        base = {'event_id': f"sb-{e['id']}", 'match_id': match_id, 'sequence': e['index'], 'minute': e['minute'],
                'second': e['second'], 'period': e['period'], 'team_id': team, 'player_id': player or '', 'x': x, 'y': y,
                'possession_id': f"sb-poss-{e.get('possession', 0)}",
                'under_pressure': True if e.get('under_pressure') else None}
        built: list[dict] = []
        if kind == 'Pass' and player:
            p = e['pass']
            ex, ey = _xy(p.get('end_location'))
            complete = 'outcome' not in p
            recipient = players.get(p.get('recipient', {}).get('id')) if complete else None
            built.append({**base, 'event_type': 'pass', 'outcome': 'success' if complete else 'failed', 'end_x': ex,
                          'end_y': ey, 'recipient_player_id': recipient if recipient != player else None,
                          'set_piece': PASS_SET_PIECES.get(p.get('type', {}).get('name'))})
        elif kind == 'Shot' and player:
            shot = e['shot']
            built.append({**base, 'event_type': 'shot', 'outcome': SHOT_OUTCOMES.get(shot['outcome']['name'], 'missed'),
                          'xg': shot.get('statsbomb_xg'), 'set_piece': SHOT_SET_PIECES.get(shot.get('type', {}).get('name')),
                          'under_pressure': base['under_pressure']})
        elif kind == 'Duel' and player and e.get('duel', {}).get('type', {}).get('name') == 'Tackle':
            won = e['duel'].get('outcome', {}).get('name') in ('Won', 'Success', 'Success In Play', 'Success Out')
            built.append({**base, 'event_type': 'tackle', 'outcome': 'success' if won else 'failed', 'under_pressure': None})
        elif kind in ('Ball Recovery', 'Interception') and player:
            failed = e.get('ball_recovery', {}).get('recovery_failure') or \
                e.get('interception', {}).get('outcome', {}).get('name') in ('Lost', 'Lost In Play', 'Lost Out')
            built.append({**base, 'event_type': 'recovery', 'outcome': 'failed' if failed else 'success', 'under_pressure': None})
        elif kind == 'Foul Committed' and player:
            foul = e.get('foul_committed', {})
            built.append({**base, 'event_type': 'foul', 'outcome': 'penalty' if foul.get('penalty') else 'free_kick',
                          'under_pressure': None})
            if foul.get('card'):
                built.append({**base, 'event_id': base['event_id'] + '-card', 'event_type': 'card',
                              'outcome': CARDS[foul['card']['name']], 'sequence': base['sequence'] * 10 + 1, 'under_pressure': None})
        elif kind == 'Bad Behaviour' and player and e.get('bad_behaviour', {}).get('card'):
            built.append({**base, 'event_type': 'card', 'outcome': CARDS[e['bad_behaviour']['card']['name']],
                          'under_pressure': None})
        elif kind == 'Substitution' and player:
            built.append({**base, 'event_type': 'substitution', 'outcome': 'success', 'under_pressure': None,
                          'replacement_player_id': players.get(e['substitution']['replacement']['id'])})
        else:
            unsupported[kind] += 1
            continue
        for data in built:
            if data['event_type'] != 'card':
                data['sequence'] = data['sequence'] * 10
            try:
                event = Event(**data)
                validator.add(event)
                accepted.append(event)
            except (TypeError, ValueError) as exc:
                rejected.append({'event_id': data['event_id'], 'type': data['event_type'], 'reason': str(exc)})
    by_type = Counter(e.event_type for e in accepted)
    return {'events': accepted, 'roster': names,
            'report': {'provider': 'StatsBomb', 'match_id': match_id, 'source_events': len(events),
                       'accepted': len(accepted), 'accepted_by_type': dict(by_type), 'rejected': rejected,
                       'not_represented': dict(unsupported.most_common()),
                       'stoppage_time_events': sum(1 for e in accepted if (e.period == 1 and e.minute >= 45)
                                                   or (e.period == 2 and e.minute >= 90))}}


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    """MatchMind's own analytics on the adapted stream: statistics and both pass networks."""
    from ..core import statistics
    from ..graph.analytics import passing_graph, roles
    events = result['events']
    names = result['roster']
    networks = {}
    for team in ('home', 'away'):
        r = roles(passing_graph(events, team, 0, 130), team, 0, 130, lambda p: names.get(p, {}).get('name', p))
        networks[team] = {'completed_passes': r['completed_passes'],
                          'hub': names.get(r['hub'], {}).get('name') if r['hub'] else None,
                          'key_link': names.get(r['connector'], {}).get('name') if r['connector'] else None}
    return {'statistics': statistics(events), 'pass_networks': networks}


def main() -> None:
    parser = argparse.ArgumentParser(description='Run MatchMind validation and analytics on StatsBomb event data.')
    parser.add_argument('events')
    parser.add_argument('--lineups')
    parser.add_argument('--home-team-id', type=int)
    args = parser.parse_args()
    events = json.loads(Path(args.events).read_text(encoding='utf-8'))
    lineups = json.loads(Path(args.lineups).read_text(encoding='utf-8')) if args.lineups else None
    result = adapt(events, lineups, args.home_team_id, match_id=f'statsbomb:{Path(args.events).stem}')
    print(json.dumps({'report': result['report'], **summarize(result)}, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
