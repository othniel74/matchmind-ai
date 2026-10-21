"""Independent cross-check against Sportmonks' official match record.

Sportmonks' football API gives the result, goals with scorers and minutes, cards, substitutions
and team statistics, but not every pass with pitch coordinates, so it is used here as a referee:
MatchMind runs on one provider's event stream (StatsBomb), and this module checks what MatchMind
computed against what Sportmonks recorded for the same match.

    python -m app.providers.sportmonks data/research/statsbomb/events.json \
        --lineups data/research/statsbomb/lineups.json --date 2022-12-18

The token is read from SPORTMONKS_API_TOKEN (backend/.env), sent in a header, and never printed.
Exact checks: score, each goal (team, minute within one minute, scorer), cards and substitutions.
Team statistics are compared too, but providers define shots, passes and fouls differently, so
those are reported as differences, not pass or fail.
"""
from __future__ import annotations
import argparse
import json
import os
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..core import statistics
from .statsbomb import adapt

API = 'https://api.sportmonks.com/v3/football'
INCLUDE = 'participants;scores;events.type;statistics.type;periods'
GOAL_TYPES = {'GOAL', 'OWNGOAL', 'PENALTY'}
CARD_TYPES = {'YELLOWCARD': 'yellow', 'REDCARD': 'red', 'YELLOWREDCARD': 'second_yellow'}
# Sportmonks statistic developer names -> MatchMind statistics keys (first name found wins).
STATS = {'shots': ('SHOTS_TOTAL',), 'shots_on_target': ('SHOTS_ON_TARGET',), 'passes': ('PASSES',),
         'completed_passes': ('SUCCESSFUL_PASSES', 'ACCURATE_PASSES'),
         'pass_completion_pct': ('SUCCESSFUL_PASSES_PERCENTAGE', 'ACCURATE_PASSES_PERCENTAGE'),
         'possession_pct': ('BALL_POSSESSION',), 'corners': ('CORNERS',), 'fouls': ('FOULS',)}


class SportmonksError(RuntimeError):
    pass


def get(path: str, token: str, **params: str) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f'{API}/{path}' + (f'?{query}' if query else ''),
                                     headers={'Authorization': token, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read()).get('message', '')
        except ValueError:
            message = ''
        hint = ' (Sportmonks may be down; try again later)' if exc.code >= 500 else ''
        raise SportmonksError(f'Sportmonks {exc.code} on /{path}: {message or exc.reason}{hint}') from None
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, 'reason', exc)
        raise SportmonksError(f'Sportmonks unreachable on /{path}: {reason} (try again later)') from None


def _norm(text: str | None) -> str:
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return ' '.join(text.lower().replace('-', ' ').split())


def same_person(short: str | None, full: str | None) -> bool:
    """'Lionel Messi' matches 'Lionel Andrés Messi Cuccittini': the surname appears in the full name."""
    a, b = _norm(short).split(), _norm(full).split()
    return bool(a and b) and a[-1] in b


def find_fixture(token: str, date: str, home: str, away: str) -> int:
    page, names = 1, []
    while True:
        data = get(f'fixtures/date/{date}', token, include='participants', page=str(page))
        for fixture in data.get('data', []):
            teams = {_norm(p['name']) for p in fixture.get('participants', [])}
            names.append(fixture.get('name', ''))
            if _norm(home) in teams and _norm(away) in teams:
                return fixture['id']
        if not data.get('pagination', {}).get('has_more'):
            break
        page += 1
    raise SportmonksError(f'No fixture for {home} v {away} on {date} in this subscription '
                          f'({len(names)} fixtures visible that day)')


def reference(fixture: dict) -> dict[str, Any]:
    """Sportmonks' record of the match, keyed by side ('home'/'away')."""
    side = {p['id']: p.get('meta', {}).get('location') for p in fixture.get('participants', [])}
    teams = {side[p['id']]: p['name'] for p in fixture.get('participants', [])}
    goals, cards = [], {t: {'yellow': 0, 'second_yellow': 0, 'red': 0} for t in ('home', 'away')}
    subs = {'home': 0, 'away': 0}
    running = (0, 0)
    for e in sorted(fixture.get('events', []), key=lambda e: (e.get('minute') or 0, e.get('extra_minute') or 0,
                                                             e.get('sort_order') or 0)):
        kind = (e.get('type') or {}).get('developer_name', '')
        team = side.get(e.get('participant_id'))
        if 'SHOOTOUT' in kind or team is None:
            continue
        minute = (e.get('minute') or 0) + (e.get('extra_minute') or 0)
        if kind in GOAL_TYPES:
            scorer_side = team if kind != 'OWNGOAL' else ('away' if team == 'home' else 'home')
            try:  # the running score ('2-1', home first) says who scored, whatever the own-goal convention
                score = tuple(int(n) for n in str(e.get('result')).split('-'))
                if len(score) == 2 and score != running:
                    scorer_side = 'home' if score[0] > running[0] else 'away'
                    running = score
            except ValueError:
                pass
            goals.append({'team': scorer_side, 'minute': minute, 'player': e.get('player_name'),
                          'own_goal': kind == 'OWNGOAL', 'penalty': kind == 'PENALTY'})
        elif kind in CARD_TYPES:
            cards[team][CARD_TYPES[kind]] += 1
        elif kind == 'SUBSTITUTION':
            subs[team] += 1
    stats: dict[str, dict[str, float]] = {'home': {}, 'away': {}}
    for s in fixture.get('statistics', []):
        team = s.get('location') or side.get(s.get('participant_id'))
        name = (s.get('type') or {}).get('developer_name')
        if team in stats and name:
            stats[team][name] = (s.get('data') or {}).get('value')
    return {'fixture_id': fixture.get('id'), 'name': fixture.get('name'), 'teams': teams,
            'score': {t: sum(g['team'] == t for g in goals) for t in ('home', 'away')},
            'goals': goals, 'cards': cards, 'substitutions': subs, 'statistics': stats}


def align(ref: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    """Use MatchMind's home/away: at neutral venues the providers can list the teams the other way round."""
    if not (_norm(ref['teams'].get('home')) == _norm(names.get('away'))
            and _norm(ref['teams'].get('away')) == _norm(names.get('home'))):
        return ref
    flip = {'home': 'away', 'away': 'home'}
    swap = lambda d: {flip[k]: v for k, v in d.items()}
    return {**ref, 'teams': swap(ref['teams']), 'score': swap(ref['score']), 'cards': swap(ref['cards']),
            'substitutions': swap(ref['substitutions']), 'statistics': swap(ref['statistics']),
            'goals': [{**g, 'team': flip[g['team']]} for g in ref['goals']], 'sides_swapped': True}


def _display_minute(event) -> int:
    """MatchMind/StatsBomb elapsed minute -> the minute a scoreboard shows, stoppage time added on."""
    return event.minute + 1


def compare(result: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    events, names = result['events'], result['roster']
    ours = statistics(events)
    our_goals = [e for e in events if e.event_type == 'shot' and e.outcome == 'goal']
    checks = []

    def check(name: str, expected: Any, actual: Any, ok: bool | None = None) -> None:
        checks.append({'check': name, 'sportmonks': expected, 'matchmind': actual,
                       'agrees': expected == actual if ok is None else ok})

    check('score', ref['score'], {t: ours[t]['goals'] for t in ('home', 'away')})
    unmatched = list(our_goals)
    for g in ref['goals']:
        hit = next((e for e in unmatched if e.team_id == g['team'] and abs(_display_minute(e) - g['minute']) <= 1
                    and (g['own_goal'] or same_person(g['player'], names.get(e.player_id, {}).get('name')))), None)
        if hit:
            unmatched.remove(hit)
        check(f"goal {g['minute']}' {ref['teams'].get(g['team'])} ({g['player']})", g['minute'],
              {'minute': _display_minute(hit), 'scorer': names.get(hit.player_id, {}).get('name')} if hit else None,
              hit is not None)
    for e in unmatched:
        check(f"goal only in MatchMind {_display_minute(e)}'", None, names.get(e.player_id, {}).get('name'), False)
    for t in ('home', 'away'):
        label = ref['teams'].get(t, t)
        # MatchMind counts a second yellow as a yellow and a red; Sportmonks records one yellow-red card.
        cards = ref['cards'][t]
        check(f'{label} yellow cards (a second yellow counts)', cards['yellow'] + cards['second_yellow'],
              ours[t]['yellow_cards'])
        check(f'{label} sendings-off', cards['red'] + cards['second_yellow'], ours[t]['red_cards'])
        check(f'{label} substitutions', ref['substitutions'][t], ours[t]['substitutions'])
    differences = []
    for t in ('home', 'away'):
        for key, candidates in STATS.items():
            value = next((ref['statistics'][t][c] for c in candidates if c in ref['statistics'][t]), None)
            if value is None:
                continue
            mine = ours[t][key]
            differences.append({'team': ref['teams'].get(t, t), 'statistic': key, 'sportmonks': value, 'matchmind': mine,
                                'difference': round(mine - value, 1),
                                'relative_pct': round(100 * (mine - value) / value, 1) if value else None})
    return {'fixture': {'id': ref['fixture_id'], 'name': ref['name'], 'teams': ref['teams'],
                        'sides_swapped': ref.get('sides_swapped', False)},
            'agreed': sum(c['agrees'] for c in checks), 'checked': len(checks), 'checks': checks,
            'statistics': differences,
            'statistics_note': 'Providers define shots, passes, possession and fouls differently; '
                               'these are differences to explain, not failures.'}


def team_names(events: list[dict], lineups: list[dict] | None, home_team_id: int | None) -> dict[str, str]:
    starting = [e for e in events if e['type']['name'] == 'Starting XI']
    ids = [e['team']['id'] for e in starting]
    home = home_team_id if home_team_id in ids else ids[0]
    return {'home' if e['team']['id'] == home else 'away': e['team']['name'] for e in starting}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check MatchMind's output on StatsBomb data against Sportmonks.")
    parser.add_argument('events')
    parser.add_argument('--lineups')
    parser.add_argument('--home-team-id', type=int)
    parser.add_argument('--date', help='match date (YYYY-MM-DD) to find the Sportmonks fixture by team names')
    parser.add_argument('--fixture-id', type=int)
    parser.add_argument('--fixture-json', help='a saved Sportmonks fixture response (no network)')
    parser.add_argument('--save', help='save the fetched Sportmonks fixture response here')
    args = parser.parse_args()
    events = json.loads(Path(args.events).read_text(encoding='utf-8'))
    lineups = json.loads(Path(args.lineups).read_text(encoding='utf-8')) if args.lineups else None
    try:
        fixture = _load_fixture(args, events, lineups)
    except SportmonksError as exc:
        raise SystemExit(str(exc))
    fixture = fixture.get('data', fixture)
    result = adapt(events, lineups, args.home_team_id, match_id=f'statsbomb:{Path(args.events).stem}')
    ref = align(reference(fixture), team_names(events, lineups, args.home_team_id))
    print(json.dumps(compare(result, ref), indent=2, ensure_ascii=False, default=str))


def _load_fixture(args: argparse.Namespace, events: list[dict], lineups: list[dict] | None) -> dict:
    if args.fixture_json:
        fixture = json.loads(Path(args.fixture_json).read_text(encoding='utf-8'))
    else:
        if os.environ.get('MATCHMIND_SKIP_DOTENV') != '1':
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
        token = os.environ.get('SPORTMONKS_API_TOKEN')
        if not token:
            raise SystemExit('Set SPORTMONKS_API_TOKEN in backend/.env')
        names = team_names(events, lineups, args.home_team_id)
        fixture_id = args.fixture_id or find_fixture(token, args.date, names['home'], names['away'])
        fixture = get(f'fixtures/{fixture_id}', token, include=INCLUDE)
        if args.save:
            Path(args.save).write_text(json.dumps(fixture, ensure_ascii=False), encoding='utf-8')
    return fixture


if __name__ == '__main__':
    main()
