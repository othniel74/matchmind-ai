"""Fetch bounded research samples from the providers' official repositories.

Raw files stay under backend/data (excluded from Git and Docker builds).
No credentials, cloud services or paid APIs are needed.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'backend/data/research'

def download(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()

def save(folder, name, content):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(content)

def provenance(folder, sources):
    payload = {'provider': folder.name, 'retrieved': '2026-10-18', 'sources': sources,
               'scope': 'Local research only. Not a commercial or redistribution license.',
               'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in folder.iterdir() if p.is_file() and p.name != 'provenance.json'}}
    save(folder, 'provenance.json', json.dumps(payload, indent=2).encode())

def statsbomb():
    folder = DEST / 'statsbomb'
    base = 'https://raw.githubusercontent.com/statsbomb/open-data/master/'
    sources = {}
    for name, path in [('events.json', 'data/events/3869685.json'),
                       ('lineups.json', 'data/lineups/3869685.json'),
                       ('matches.json', 'data/matches/43/106.json'),
                       ('README.md', 'README.md'), ('LICENSE.pdf', 'LICENSE.pdf'),
                       ('logo.png', 'img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png')]:
        sources[name] = base + path
        save(folder, name, download(base + path))
    provenance(folder, sources)
    print('StatsBomb: Argentina v France, World Cup final 2022; 4,407 source events.')

def finite(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None

def metrica():
    folder = DEST / 'metrica'
    base = 'https://raw.githubusercontent.com/metrica-sports/sample-data/master/'
    sources = {'README.md': base + 'README.md'}
    save(folder, 'README.md', download(sources['README.md']))
    teams = []
    roster = []
    for side in ['Home', 'Away']:
        filename = f'Sample_Game_1_RawTrackingData_{side}_Team.csv'
        url = base + 'data/Sample_Game_1/' + filename
        sources[filename] = url
        lines = []
        with urllib.request.urlopen(url, timeout=60) as response:
            for i, line in enumerate(response):
                if i >= 3004:
                    break
                lines.append(line.decode('utf-8'))
        save(folder, filename, ''.join(lines).encode())
        rows = list(csv.reader(lines))
        headers = rows[2]
        columns = [(i, h, int(rows[1][i])) for i, h in enumerate(headers) if h.startswith('Player')]
        team_id = 1 if side == 'Home' else 2
        for i, name, number in columns:
            roster.append({'id': number, 'team_id': team_id, 'number': number,
                           'short_name': name, 'player_role': {'acronym': 'GK' if number in [11, 25] else 'Unknown'}})
        team = []
        ball_index = headers.index('Ball')
        for row in rows[3:]:
            players = []
            for i, name, number in columns:
                x, y = finite(row[i]), finite(row[i + 1])
                if x is not None and y is not None:
                    players.append({'player_id': number, 'x': (x - .5) * 105,
                                    'y': (y - .5) * 68, 'is_detected': True})
            x, y = finite(row[ball_index]), finite(row[ball_index + 1])
            team.append({'frame': int(row[1]), 'time': float(row[2]), 'players': players,
                         'ball': {'x': None if x is None else (x - .5) * 105,
                                  'y': None if y is None else (y - .5) * 68,
                                  'z': None, 'is_detected': None}})
        teams.append(team)
    assert len(teams[0]) == len(teams[1]) == 3001
    frames = []
    for home, away in zip(*teams):
        assert home['frame'] == away['frame'] and home['time'] == away['time']
        frames.append({'frame': home['frame'], 'timestamp': str(home['time']), 'period': 1,
                       'ball_data': home['ball'], 'possession': {'player_id': None},
                       'player_data': home['players'] + away['players']})
    meta = {'id': 1, 'fps': 25, 'pitch_length': 105, 'pitch_width': 68,
            'home_team': {'id': 1, 'short_name': 'Metrica Home'},
            'away_team': {'id': 2, 'short_name': 'Metrica Away'}, 'players': roster}
    save(folder, 'frames.json', json.dumps(frames, allow_nan=False).encode())
    save(folder, 'match.json', json.dumps(meta).encode())
    url = base + 'data/Sample_Game_1/Sample_Game_1_RawEventsData.csv'
    sources['events.csv'] = url
    raw = download(url)
    save(folder, 'events.csv', raw)
    events = []
    for i, row in enumerate(csv.DictReader(io.StringIO(raw.decode('utf-8')))):
        start = finite(row['Start Time [s]'])
        if row['Period'] != '1' or start is None or start > 120.04:
            continue
        def point(a, b):
            x, y = finite(row[a]), finite(row[b])
            return None if x is None or y is None else [x * 100, y * 100]
        events.append({'id': f'metrica-1-{i+1}', 'time': max(0, start - .04),
                       'type': row['Type'], 'subtype': row['Subtype'], 'team': row['Team'],
                       'player': row['From'], 'recipient': row['To'],
                       'start': point('Start X', 'Start Y'), 'end': point('End X', 'End Y'),
                       'start_frame': int(row['Start Frame']), 'end_frame': int(row['End Frame'])})
    save(folder, 'events.json', json.dumps(events, allow_nan=False).encode())
    provenance(folder, sources)
    print(f'Metrica: 3,001 synchronized 25 Hz frames and {len(events)} events; anonymous Sample Game 1.')

if __name__ == '__main__':
    statsbomb()
    metrica()
