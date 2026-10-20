from dataclasses import replace
import pytest
from app.core import Event, generate_match, statistics, detect_insights, validate_event_stream, validate_insight


def test_generated_events_are_valid_for_multiple_seeds():
    for seed in (0, 1, 42, 20261020):
        validate_event_stream(generate_match(seed))


def test_pass_stats_and_third_entries_exact():
    events = [
        Event('a','m',1,1,0,'home','p','pass',60,40,80,40,'success','pos1'),
        Event('b','m',2,1,15,'home','p','pass',20,40,80,40,'failed','pos1'),
        Event('c','m',3,1,30,'away','p','shot',80,50),
    ]
    stats = statistics(events)
    assert stats['home']['passes'] == 2
    assert stats['home']['completed_passes'] == 1
    assert stats['home']['pass_completion_pct'] == 50
    assert stats['home']['final_third_entries'] == 1
    assert stats['away']['shots'] == 1


def test_duplicate_events_rejected():
    events = generate_match()
    with pytest.raises(ValueError, match='Duplicate'):
        validate_event_stream([events[0], events[0]])


def test_invalid_pitch_coordinates_rejected():
    event = replace(generate_match()[0], x=101)
    with pytest.raises(ValueError, match='coordinates'):
        validate_event_stream([event])


def test_tampered_insight_evidence_rejected():
    events = generate_match()
    found = [i for minute in range(20,91) for i in detect_insights([e for e in events if e.minute < minute],minute)]
    assert found, 'Scenario should produce at least one tactical insight'
    item = found[0]
    visible = [e for e in events if e.minute < item['minute']]
    assert validate_insight(item, visible)
    assert not validate_insight({**item,'current_count':item['current_count']+1},visible)
    assert not validate_insight({**item,'evidence_event_ids':['fake']},visible)


def test_no_future_evidence_leakage():
    events = generate_match()
    for minute in range(20,91):
        visible = [e for e in events if e.minute < minute]
        by_id = {e.event_id:e for e in visible}
        for insight in detect_insights(visible, minute):
            assert all(by_id[i].minute < minute for i in insight['evidence_event_ids'])
