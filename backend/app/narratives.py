"""Evidence-gated, deterministic multi-role narrative workflow.

This is a tested local fallback and orchestration contract, NOT Microsoft Agent Framework.
The agent workflow (agent_workflow.py) rephrases these verified narratives when a model
is configured; this module stays the source of trusted wording in every language.
"""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator
from .core import Event, validate_insight
from .languages import SUPPORTED, language as language_spec
from .squads import CLUBS

class AudienceRequest(BaseModel):
    minute: int = Field(default=67, ge=20, le=90)
    seed: int = Field(default=20261020, ge=0, le=2147483647)
    audience: Literal['analyst', 'fan', 'broadcast'] = 'fan'
    language: str = 'en'

    @field_validator('language')
    @classmethod
    def supported_language(cls, value: str) -> str:
        if value not in SUPPORTED:
            raise ValueError(f'language must be one of {", ".join(SUPPORTED)}')
        return value

class Narrative(BaseModel):
    insight_id: str
    audience: str
    language: str
    direction: Literal['ltr', 'rtl'] = 'ltr'
    headline: str
    body: str
    evidence_event_ids: list[str]
    status: Literal['approved'] = 'approved'
    engine: Literal['deterministic_fallback'] = 'deterministic_fallback'
    trace: list[str]


def publish_narratives(events: list[Event], insights: list[dict[str, Any]], audience: str, language: str) -> list[Narrative]:
    """Four explicit stages: select, interpret, narrate, personalize; gate before publishing."""
    spec = language_spec(language)
    results: list[Narrative] = []
    for insight in insights:
        trace = ['insight_selection']
        if not validate_insight(insight, events):
            continue
        trace.append('tactical_interpretation')
        team = 'away' if insight['team_id'] == 'away' else 'home'
        values = {'prev': insight['previous_count'], 'curr': insight['current_count'], 'club': CLUBS[team].short}
        trace.append('narrative_generation')
        headline = spec.narrative['headline'].format(**values)
        body = spec.narrative[audience].format(**values)
        trace.extend(['audience_personalization', 'evidence_validation', 'publication'])
        results.append(Narrative(insight_id=insight['id'], audience=audience, language=language,
                                 direction=spec.direction, headline=headline, body=body,
                                 evidence_event_ids=insight['evidence_event_ids'], trace=trace))
    return results
