"""Evidence-gated, clock-synchronized broadcast overlay contracts (synthetic demo)."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from .core import Event, validate_insight
from .narratives import publish_narratives
from .languages import language as language_spec

class Overlay(BaseModel):
    """Machine-readable overlay for a rendering partner: what to show, when, for how long, and why."""
    overlay_id: str
    match_id: str
    insight_id: str
    overlay_type: str  # advanced_activity_increase, or a moment kind (goal, red_card, top_speed, ...)
    match_clock_seconds: int = Field(ge=0, le=5400)
    duration_ms: int = Field(default=8000, ge=1000, le=30000)
    priority: int = Field(default=7, ge=1, le=10)
    audience_mode: Literal['fan','analyst','broadcast']
    language: str
    direction: Literal['ltr', 'rtl'] = 'ltr'
    headline: str
    body: str
    metric_label: str = ''
    previous_value: float | None = None
    current_value: float | None = None
    team_id: str | None = None
    player_ids: list[str] = []
    player_names: list[str] = []
    favourite_club: bool = False
    favourite_player: bool = False
    facts: dict = {}
    evidence_event_ids: list[str]
    validation_status: Literal['approved'] = 'approved'
    source: Literal['synthetic'] = 'synthetic'


def create_overlays(events: list[Event], insights: list[dict], audience: str='broadcast', language: str='en') -> list[Overlay]:
    """Publish only validated insights and matching verified narratives."""
    narratives = {n.insight_id:n for n in publish_narratives(events, insights, audience, language)}
    match_id = events[0].match_id if events else 'demo-001'
    output: list[Overlay] = []
    for insight in insights:
        if not validate_insight(insight, events) or insight['id'] not in narratives:
            continue
        narrative = narratives[insight['id']]
        if narrative.evidence_event_ids != insight['evidence_event_ids']:
            continue
        output.append(Overlay(
            overlay_id=f"ovl-{insight['id']}-{audience}-{language}",
            match_id=match_id, insight_id=insight['id'],
            overlay_type='advanced_activity_increase',
            match_clock_seconds=insight['minute']*60, audience_mode=audience,
            language=language, direction=narrative.direction, headline=narrative.headline, body=narrative.body,
            metric_label=language_spec(language).metric_label,
            previous_value=insight['previous_count'], current_value=insight['current_count'],
            evidence_event_ids=insight['evidence_event_ids']))
    return output


def active_overlays(overlays: list[Overlay], match_clock_seconds: int) -> list[Overlay]:
    """Suppress future and expired overlays; stable order for the render queue."""
    return sorted((o for o in overlays if o.match_clock_seconds <= match_clock_seconds < o.match_clock_seconds + o.duration_ms / 1000),
                  key=lambda o: (-o.priority, o.match_clock_seconds, o.overlay_id))


def moment_overlays(moments: list[dict], match_id: str, audience: str, language: str) -> list[Overlay]:
    """Overlays for personalized moments (already rendered and filtered by experience.py)."""
    output = []
    for m in moments:
        if m['kind'] == 'activity':
            continue  # covered by the evidence-gated insight overlay above
        output.append(Overlay(
            overlay_id=f"ovl-{m['id']}-{audience}-{language}", match_id=match_id, insight_id=m['id'],
            overlay_type=m['kind'], match_clock_seconds=m['clock_seconds'], duration_ms=m['duration_ms'],
            priority=m['priority'], audience_mode=audience, language=language, direction=m['direction'],
            headline=m['headline'], body=m['body'], team_id=m['team_id'], player_ids=m['player_ids'],
            player_names=m['player_names'], favourite_club=m['favourite_club'],
            favourite_player=m['favourite_player'], facts={k: v for k, v in m['facts'].items() if k != 'definition'},
            evidence_event_ids=m['evidence_event_ids']))
    return output
