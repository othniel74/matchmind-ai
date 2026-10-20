"""Live, event-by-event pipeline: ingest -> interpret -> explain -> render -> personalize.

A LiveMatch accepts one event at a time from any feed. Each event is validated against the
stream so far, event-driven moments (goals, chances, cards, substitutions, milestones) are
detected immediately, and per-minute analysis (dynamics, physical tags) runs when a minute
completes. Output messages are personalized and rendered for one viewer profile.
"""
from __future__ import annotations
from collections import OrderedDict
from typing import Any
from uuid import uuid4
from .core import Event, StreamValidator, pass_difficulty, statistics
from .dynamics import state_at
from .experience import Profile, relevance
from .moments import detect_moments, render
from .players import PASS_MILESTONES
from .squads import name

# Kinds that an individual event can trigger; the rest need a completed minute.
EVENT_KINDS = {'goal', 'big_chance', 'red_card', 'yellow_card', 'substitution', 'brace', 'hat_trick', 'passes'}


def enrich(e: Event) -> dict[str, Any]:
    data = e.json()
    data.update(clock_seconds=e.minute * 60 + e.second, player_name=name(e.player_id),
                recipient_name=name(e.recipient_player_id) if e.recipient_player_id else None,
                replacement_name=name(e.replacement_player_id) if e.replacement_player_id else None,
                pass_difficulty=pass_difficulty(e) if e.event_type == 'pass' else None)
    return data


class LiveMatch:
    def __init__(self, seed: int, profile: Profile):
        self.seed = seed
        self.profile = profile.validate()
        self.events: list[Event] = []
        self.validator = StreamValidator()
        self.seen: set[str] = set()
        self.completed = 0          # minutes fully ingested
        self.completed_passes: dict[str, int] = {}

    def ingest(self, event: Event) -> list[dict[str, Any]]:
        """Validate and process one event; returns the messages to publish, in order."""
        self.validator.add(event)  # raises ValueError and changes nothing if the event is invalid
        messages: list[dict[str, Any]] = []
        while self.completed < event.minute:  # minutes before this event are now complete
            self.completed += 1
            messages += self._moments(self.completed, None)
            messages.append(self.state())
        self.events.append(event)
        messages.append({'type': 'event', 'event': enrich(event)})
        if self._triggers(event):
            messages += self._moments(event.minute + 1, EVENT_KINDS)
        return messages

    def finish(self) -> list[dict[str, Any]]:
        """Close the final minutes once the feed ends."""
        messages: list[dict[str, Any]] = []
        while self.completed < 90:
            self.completed += 1
            messages += self._moments(self.completed, None)
            messages.append(self.state())
        return messages

    def _triggers(self, e: Event) -> bool:
        if e.event_type in {'shot', 'card', 'substitution'}:
            return True
        if e.event_type == 'pass' and e.outcome == 'success':
            count = self.completed_passes.get(e.player_id, 0) + 1
            self.completed_passes[e.player_id] = count
            return count in PASS_MILESTONES
        return False

    def _moments(self, minute: int, kinds: set[str] | None) -> list[dict[str, Any]]:
        messages = []
        for m in detect_moments(self.events, self.seed, minute):
            if m['id'] in self.seen or (kinds is not None and m['kind'] not in kinds):
                continue
            self.seen.add(m['id'])
            shown, score, flags = relevance(m, self.profile)
            if shown:
                messages.append({'type': 'moment', 'moment': {**m, **render(m, self.profile.language), **flags,
                                 'relevance': score, 'player_names': [name(p) for p in m['player_ids']]}})
        return messages

    def state(self) -> dict[str, Any]:
        state = state_at(self.events, self.completed)
        return {'type': 'state', 'minute': self.completed, 'events_ingested': len(self.events),
                'statistics': statistics(self.events),
                'dynamics': None if state is None else {'control': state['control'], 'tempo': state['tempo'],
                                                        'momentum': state['momentum']}}


class LiveSessions:
    """In-memory sessions for external feeds; oldest sessions are dropped beyond the cap."""
    def __init__(self, cap: int = 20):
        self.cap = cap
        self.sessions: OrderedDict[str, LiveMatch] = OrderedDict()

    def create(self, seed: int, profile: Profile) -> str:
        session_id = uuid4().hex
        self.sessions[session_id] = LiveMatch(seed, profile)
        while len(self.sessions) > self.cap:
            self.sessions.popitem(last=False)
        return session_id

    def get(self, session_id: str) -> LiveMatch | None:
        return self.sessions.get(session_id)


SESSIONS = LiveSessions()
