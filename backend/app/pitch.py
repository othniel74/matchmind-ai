"""A role-constrained illustrative 4-3-3; canonical actions stay separate.

Event coordinates are activity samples, not player-tracking trajectories. They
must not teleport a player out of their formation or pull a keeper into attack.
Each entry's player_id names a stable formation slot (the renderers key on it);
occupant_id is the player currently filling that slot after substitutions.
"""
from __future__ import annotations
import math
from .core import Event, ON_BALL_TYPES, SENDING_OFF
from .squads import PLAYERS

FORMATION = ((8, 50), (25, 14), (23, 38), (23, 62), (25, 86),
             (44, 25), (42, 50), (44, 75), (65, 16), (68, 50), (65, 84))
ROLES = ('GK', 'RB', 'RCB', 'LCB', 'LB', 'RCM', 'CDM', 'LCM', 'RW', 'ST', 'LW')


def pitch_state(events: list[Event], minute: int) -> dict:
    if not 0 <= minute <= 90:
        raise ValueError('Invalid pitch minute')
    visible = sorted((event for event in events if event.minute < minute), key=lambda e: (e.minute, e.second, e.sequence))
    occupants = {f'{team}-{i:02}': f'{team}-{i:02}' for team in ('home', 'away') for i in range(1, 12)}
    slot_of = {player: player for player in occupants}
    for event in visible:
        slot = slot_of.get(event.player_id)
        if slot is None:
            continue
        if event.event_type == 'substitution' and event.replacement_player_id:
            occupants[slot] = event.replacement_player_id
            slot_of[event.replacement_player_id] = slot
        elif event.event_type == 'card' and event.outcome in SENDING_OFF:
            occupants[slot] = None
    on_ball = [event for event in visible if event.event_type in ON_BALL_TYPES]
    latest = on_ball[-1] if on_ball else None

    def global_x(team: str, x: float) -> float:
        return x if team == 'home' else 100 - x

    ball = {'x': 50.0, 'y': 50.0, 'source_event_id': None}
    active = None
    if latest:
        end_x = latest.end_x if latest.event_type == 'pass' and latest.end_x is not None else latest.x
        end_y = latest.end_y if latest.event_type == 'pass' and latest.end_y is not None else latest.y
        ball = {'x': global_x(latest.team_id, end_x), 'y': end_y, 'source_event_id': latest.event_id}
        active = latest.recipient_player_id if latest.event_type == 'pass' and latest.outcome == 'success' else latest.player_id

    # Team shape follows a low-pass filtered passage of play, never one random
    # event actor. Replaying the prefix makes seeks deterministic and causal.
    # Smoothing uses elapsed seconds so shape does not depend on event density.
    centre_x, centre_y, home_share = 50.0, 50.0, .5
    previous_clock = 0
    for offset, event in enumerate(on_ball):
        clock = event.minute * 60 + event.second
        elapsed = max(1, clock - previous_clock)
        previous_clock = clock
        recent = [e for e in on_ball[max(0, offset - 60):offset + 1] if clock - (e.minute * 60 + e.second) <= 180]
        share = sum(e.team_id == 'home' for e in recent) / len(recent)
        centre_x += (global_x(event.team_id, event.x) - centre_x) * (1 - math.exp(-elapsed / 420))
        centre_y += (event.y - centre_y) * (1 - math.exp(-elapsed / 590))
        home_share += (share - home_share) * (1 - math.exp(-elapsed / 370))

    players = []
    for team in ('home', 'away'):
        direction = 1 if team == 'home' else -1
        share = home_share if team == 'home' else 1 - home_share
        for index, (anchor_x, anchor_y) in enumerate(FORMATION, 1):
            player_id = f'{team}-{index:02}'
            occupant = occupants[player_id]
            x = global_x(team, anchor_x)
            y = float(anchor_y if team == 'home' else 100 - anchor_y)
            if index == 1:
                # A keeper shuffles with play inside their own penalty area.
                x += direction * max(-2, min(2, (direction * (centre_x - 50)) * .035))
                y += max(-10, min(10, (centre_y - 50) * .22))
            else:
                # Back four, midfield three and front three move as a unit.
                # Possession advances the block; defending narrows its width.
                x += (centre_x - 50) * .14 + direction * (share - .5) * 12
                compactness = .88 + share * .12
                y = 50 + (y - 50) * compactness + (centre_y - 50) * .12
            facing_x = max(20, ball['x']) if team == 'home' else min(80, ball['x'])
            listed = PLAYERS.get(occupant or '')
            number = listed.shirt if listed else (int(occupant.rsplit('-', 1)[1]) if occupant else index)
            players.append({'player_id': player_id, 'occupant_id': occupant, 'on_pitch': occupant is not None,
                            'team_id': team, 'number': number, 'name': listed.name if listed else None,
                            'role': ROLES[index - 1], 'x': round(max(3, min(97, x)), 2),
                            'y': round(max(4, min(96, y)), 2),
                            'facing_x': facing_x, 'facing_y': ball['y'],
                            'active': occupant is not None and occupant == active,
                            'position_source': 'illustrative_formation',
                            'source_event_id': None})
    action = None
    if latest:
        action = {'event_id': latest.event_id, 'team_id': latest.team_id, 'player_id': latest.player_id,
                  'player_name': PLAYERS[latest.player_id].name if latest.player_id in PLAYERS else None,
                  'type': latest.event_type, 'outcome': latest.outcome,
                  'from_x': global_x(latest.team_id, latest.x), 'from_y': latest.y,
                  'to_x': ball['x'], 'to_y': ball['y']}
    return {'players': players, 'ball': ball, 'action': action, 'minute': minute,
            'formation': '4-3-3', 'mode': 'illustrative_formation_simulation',
            'disclaimer': 'Synthetic 4-3-3 simulation: player positions are illustrative; event coordinates are separate activity cues, not tracking data. Slots track substitutions; a sent-off player leaves the slot empty.'}
