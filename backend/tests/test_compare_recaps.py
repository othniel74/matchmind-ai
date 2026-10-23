"""Measurement reports must not mistake fallbacks or errors for agent success."""
import asyncio

from evaluation.compare_recaps import compare, summarize


def test_latency_summary_separates_errors_fallbacks_and_unmeasured_cost():
    rows = [
        {'mode': 'full_workflow', 'status': 'ok', 'duration_ms': 100, 'checker_accepted': True},
        {'mode': 'full_workflow', 'status': 'fallback', 'duration_ms': 200},
        {'mode': 'full_workflow', 'status': 'error', 'duration_ms': 999},
    ]
    result = summarize(rows)['full_workflow']
    assert result == {'runs': 3, 'errors': 1, 'fallbacks': 1, 'p50_ms': 100, 'p95_ms': 200,
                      'checker_accepted': 1, 'checker_evaluated': 1, 'cost_usd': None}


def test_offline_comparison_never_constructs_a_model_client(monkeypatch):
    from app.agents import FoundryAgentRuntime

    def forbidden(*args, **kwargs):
        raise AssertionError('Offline benchmark attempted a model call')

    monkeypatch.setattr(FoundryAgentRuntime, '_client', forbidden)
    rows = asyncio.run(compare([20261020], [45], ['en']))
    assert len(rows) == 1 and rows[0]['mode'] == 'template'
    assert rows[0]['status'] == 'ok' and rows[0]['text']
    assert rows[0]['checker_accepted'] is None
