import asyncio
import pytest
from app.agents import FoundryAgentRuntime
from app.telemetry import configure_tracing

pytest.importorskip('opentelemetry.sdk')
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope='module', autouse=True)
def provider():
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
    trace.set_tracer_provider(tracer_provider)
    yield


def test_narrative_run_spans_nest_agent_and_workflow_spans():
    from tests.test_agents import fixture, honest, scripted_client
    EXPORTER.clear()
    events, insights = fixture()
    result = asyncio.run(FoundryAgentRuntime(scripted_client(honest())).run(events, insights, 'fan', 'fr'))
    spans = EXPORTER.get_finished_spans()
    root = next(s for s in spans if s.name == 'matchmind.narrative_run')
    assert root.attributes['matchmind.run_id'] == result.trace.run_id
    assert root.attributes['matchmind.language'] == 'fr'
    assert root.attributes['matchmind.engine'] == 'microsoft_agent_framework'
    nested = [s for s in spans if s.context.trace_id == root.context.trace_id and s is not root]
    names = ' '.join(s.name for s in nested)
    # Framework spans: one agent invocation per writer and the fact checker, plus workflow executors.
    for agent in ('tactical-analyst', 'match-storyteller', 'audience-editor', 'fact-checker'):
        assert agent in names, names
    assert any('workflow' in s.name or 'executor' in s.name for s in nested), names
    # Prompts and generated text stay out of telemetry by default.
    exported = ' '.join(str(v) for s in spans for v in s.attributes.values())
    assert 'final third' not in exported and 'advanced areas' not in exported


def test_tracing_mode_validation(monkeypatch):
    import app.telemetry as telemetry
    monkeypatch.setattr(telemetry, '_configured', None)
    monkeypatch.setenv('MATCHMIND_TRACING', 'loud')
    with pytest.raises(RuntimeError):
        configure_tracing()
    monkeypatch.setenv('MATCHMIND_TRACING', 'otlp')
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_ENDPOINT', raising=False)
    with pytest.raises(RuntimeError):
        configure_tracing()
    monkeypatch.setenv('MATCHMIND_TRACING', 'off')
    assert configure_tracing() == 'off'
