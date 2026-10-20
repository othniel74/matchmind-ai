"""Fictional clubs and squads for the synthetic match.

Player IDs (home-01 ... home-16) are the stable keys used by events, pitch slots and
evidence; this registry adds display names, shirt numbers and positions. Every club and
player is invented and must not resemble a real club or player.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Club:
    team_id: str
    name: str
    short: str
    code: str
    primary: str
    secondary: str


@dataclass(frozen=True)
class Player:
    player_id: str
    team_id: str
    name: str
    shirt: int
    position: str   # GK, DF, MF, FW
    role: str       # starting slot role, or SUB


CLUBS = {
    'home': Club('home', 'Calderbrook FC', 'Calderbrook', 'CAL', '#e4485b', '#f7f1e3'),
    'away': Club('away', 'Merridge Athletic', 'Merridge', 'MER', '#3d8fd6', '#0f2238'),
}

# Starting slots follow the illustrative 4-3-3 in core.SLOTS; 12-16 are substitutes.
_ROLES = ('GK', 'RB', 'RCB', 'LCB', 'LB', 'RCM', 'CDM', 'LCM', 'RW', 'ST', 'LW', 'SUB', 'SUB', 'SUB', 'SUB', 'SUB')
_POSITIONS = ('GK', 'DF', 'DF', 'DF', 'DF', 'MF', 'MF', 'MF', 'FW', 'FW', 'FW', 'DF', 'MF', 'MF', 'FW', 'FW')
_SHIRTS = (1, 2, 5, 4, 3, 8, 6, 10, 7, 9, 11, 14, 16, 18, 19, 21)
_NAMES = {
    'home': ('Arno Velde', 'Kayode Ashworth', 'Luca Ferrandi', 'Mats Holvik', 'Idris Kamara-Lowe',
             'Theo Marchetti', 'Samuel Adeyemi-Brook', 'Yusuf Delacroix', 'Ennis Varga', 'Callum Rhodes',
             'Nico Albarrán', 'Owen Tackett', 'Jae-won Seo', 'Emeka Lindqvist', 'Rúben Castellar',
             'Dario Petković'),
    'away': ('Fabian Kroll', 'Malik Osei-Barnes', 'Pedro Valença', 'Henrik Sandvold', 'Aiden Mburu',
             'Kofi Asante-Reyes', 'Lorenzo Bassi', 'Amadou Fofanah-Clarke', 'Jonah Whitlock',
             'Bastien Moreau-Diallo', 'Ivo Brankov', 'Elias Thornbury', 'Sami Haddad', 'Tariq Benali',
             'Marco Ferreira-Lund', 'Desmond Achterberg'),
}

PLAYERS: dict[str, Player] = {
    f'{team}-{index:02}': Player(f'{team}-{index:02}', team, name, _SHIRTS[index - 1],
                                 _POSITIONS[index - 1], _ROLES[index - 1])
    for team, names in _NAMES.items() for index, name in enumerate(names, 1)
}


def player(player_id: str | None) -> Player | None:
    return PLAYERS.get(player_id or '')


def name(player_id: str | None) -> str:
    """Display name, or the raw ID for players outside the registry (legacy fixtures)."""
    found = player(player_id)
    return found.name if found else (player_id or '')


def squads() -> dict:
    return {'clubs': {team: vars(club) for team, club in CLUBS.items()},
            'players': [vars(p) for p in PLAYERS.values()]}
