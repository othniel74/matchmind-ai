"""Fact-check rules found in live runs: statements that name no single team, in-progress recaps,
and the per-statement verdicts the run trace shows."""
import pytest

pytest.importorskip('agent_framework')

from app.agent_workflow import Draft, NarrativeJob, Statements, in_progress_note, verify_statements  # noqa: E402
from app.claims import measure  # noqa: E402
from app.core import generate_match  # noqa: E402
from app.recap import recap_facts  # noqa: E402

EVENTS = generate_match()
FLAGS = dict.fromkeys(('mentions_match_time', 'gives_cause', 'mentions_chances_or_threat', 'is_prediction',
                       'judges_performance', 'claims_dominance'), False)


def stmt(quote, kind, team=None, relation=None, metric=None):
    return {'quote': quote, 'type': kind, 'team': team, 'relation': relation, 'player': None, 'metric': metric,
            'intensity': 'neutral', **FLAGS}


def minute_where(condition):
    return next(m for m in range(1, 91) if condition(m))


def test_level_score_with_no_named_team_is_verified():
    level = minute_where(lambda m: recap_facts(EVENTS, m)['result']['home'] == 'level')
    text = 'The teams are level'
    verdicts = []
    failure, claims, rejected = verify_statements([stmt(text, 'result', relation='level')], text, None, EVENTS,
                                                  level, verdicts)
    assert failure is None and claims and verdicts == [{'quote': text, 'type': 'result', 'supported': True,
                                                        'reason': None}]
    ahead = minute_where(lambda m: recap_facts(EVENTS, m)['result']['home'] != 'level')
    failure, _, rejected = verify_statements([stmt(text, 'result', relation='level')], text, None, EVENTS, ahead)
    assert failure == 'contradicts_result' and rejected == [text]


def test_equal_comparison_with_no_named_team_is_checked_against_both():
    equal = minute_where(lambda m: measure(EVENTS, 'corners', 'home', m)[0] == measure(EVENTS, 'corners', 'away', m)[0])
    text = 'Both teams had the same number of corners'
    assert verify_statements([stmt(text, 'comparison', relation='equal', metric='corners')], text, None, EVENTS,
                             equal)[0] is None
    unequal = minute_where(lambda m: measure(EVENTS, 'corners', 'home', m)[0] != measure(EVENTS, 'corners', 'away', m)[0])
    assert verify_statements([stmt(text, 'comparison', relation='equal', metric='corners')], text, None, EVENTS,
                             unequal)[0] == 'contradicts_claims'


def test_every_recap_writer_is_told_when_the_match_is_still_going():
    draft = lambda minute: Draft(NarrativeJob(EVENTS, [], 'fan', 'en', recap_minute=minute), [], [])
    assert 'still being played' in in_progress_note(draft(60)) and 'never as won' in in_progress_note(draft(60))
    assert in_progress_note(draft(90)) == ''
    assert in_progress_note(Draft(NarrativeJob(EVENTS, [], 'fan', 'en'), [], [])) == ''


def test_structured_output_schema_requires_every_field():
    schema = Statements.model_json_schema()
    item = schema['$defs']['Statement']
    assert set(item['required']) == set(item['properties'])  # strict mode: every field answered
    assert set(FLAGS) <= set(item['properties'])
