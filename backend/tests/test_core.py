from app.core import generate_match, statistics, detect_insights

def test_reproducible():
    assert generate_match(123) == generate_match(123)
    assert generate_match(123) != generate_match(124)

def test_unique_ordered_events():
    events = generate_match()
    assert 900 <= len(events) <= 1300
    assert len({e.event_id for e in events}) == len(events)
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))

def test_stats_consistency():
    events = generate_match()
    s = statistics(events)
    assert s['home']['events'] + s['away']['events'] == len(events)
    for team in ('home', 'away'):
        assert s[team]['completed_passes'] <= s[team]['passes']
        assert 0 <= s[team]['pass_completion_pct'] <= 100

def test_insight_evidence_exists():
    events = generate_match()
    ids = {e.event_id for e in events}
    for minute in range(20, 91):
        for insight in detect_insights([e for e in events if e.minute < minute], minute):
            assert insight['validated']
            assert set(insight['evidence_event_ids']) <= ids
