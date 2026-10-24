"""The synthetic matches a viewer can pick in the workspace.

Every seed gives a different, reproducible match; any seed works through the API. These are a
varied handful for the picker, with the featured match first (the video and the live feed tell
its story). Labels are computed from the events, never written by hand.
"""
from __future__ import annotations
from functools import lru_cache
from typing import Any

FEATURED = 20261020
SEEDS = (FEATURED, 20261068, 20261026, 20261032, 20261036, 20261058)


@lru_cache(maxsize=None)
def describe(seed: int) -> dict[str, Any]:
    from .core import generate_match
    events = generate_match(seed)
    goals = [e for e in events if e.event_type == 'shot' and e.outcome == 'goal']
    home = sum(e.team_id == 'home' for e in goals)
    away = len(goals) - home
    reds = sum(e.event_type == 'card' and e.outcome in ('red', 'second_yellow') for e in events)
    tags = []
    if goals and home != away and (goals[0].team_id == 'home') != (home > away):
        tags.append('comeback')
    if goals and goals[-1].minute >= 85 and abs(home - away) <= 1:
        tags.append('late goal')
    if reds:
        tags.append(f'{reds} red card' + ('s' if reds > 1 else ''))
    if not goals:
        tags.append('goalless')
    elif home == away:
        tags.append('draw')
    return {'seed': seed, 'featured': seed == FEATURED, 'score': {'home': home, 'away': away}, 'tags': tags}


def catalogue() -> list[dict[str, Any]]:
    return [describe(seed) for seed in SEEDS]
