"""OpenTelemetry tracing for the agent workflow.

MATCHMIND_TRACING selects the exporter:
- off (default): no exporter is configured.
- console: spans are printed to stdout, for local debugging.
- otlp: spans go to OTEL_EXPORTER_OTLP_ENDPOINT (for example a local collector or Aspire dashboard).
- azure_monitor: spans go to Application Insights via APPLICATIONINSIGHTS_CONNECTION_STRING
  (requires the optional azure-monitor-opentelemetry package).

Agent Framework instruments agents, chat calls and workflow executors itself. Prompt and
message content is never exported unless MATCHMIND_TRACE_SENSITIVE=true.
"""
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Any, Iterator

MODES = ('off', 'console', 'otlp', 'azure_monitor')
_configured: str | None = None


def configure_tracing() -> str:
    """Configure exporters once at startup; return the active mode."""
    global _configured
    if _configured is not None:
        return _configured
    mode = (os.getenv('MATCHMIND_TRACING') or 'off').strip().lower()
    if mode not in MODES:
        raise RuntimeError(f'MATCHMIND_TRACING must be one of {", ".join(MODES)}')
    sensitive = (os.getenv('MATCHMIND_TRACE_SENSITIVE') or 'false').lower() == 'true'
    if mode == 'azure_monitor':
        if not os.getenv('APPLICATIONINSIGHTS_CONNECTION_STRING'):
            raise RuntimeError('azure_monitor tracing needs APPLICATIONINSIGHTS_CONNECTION_STRING')
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
        except ImportError as exc:
            raise RuntimeError('Install azure-monitor-opentelemetry for azure_monitor tracing') from exc
        from opentelemetry.sdk.resources import Resource
        options = {'resource': Resource.create({'service.name': 'matchmind-backend'})}
        if not os.getenv('OTEL_TRACES_SAMPLER'):
            # The distro defaults to rate-limited sampling (5/s), which dropped most spans of a
            # live run. An audit trail of agent decisions needs every span.
            options['sampling_ratio'] = 1.0
        # Skip the Azure VM metadata probe off Azure; set OTEL_EXPERIMENTAL_RESOURCE_DETECTORS
        # (for example "azure_app_service,azure_vm") when hosted in Azure.
        os.environ.setdefault('OTEL_EXPERIMENTAL_RESOURCE_DETECTORS', 'otel')
        configure_azure_monitor(**options)
        from agent_framework.observability import enable_instrumentation
        enable_instrumentation(enable_sensitive_data=sensitive)
    elif mode in ('console', 'otlp'):
        from agent_framework.observability import configure_otel_providers
        if mode == 'otlp' and not os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT'):
            raise RuntimeError('otlp tracing needs OTEL_EXPORTER_OTLP_ENDPOINT')
        options = {}
        if mode == 'otlp':
            # The pinned exporter is OTLP over HTTP (opentelemetry-exporter-otlp-proto-http).
            options['otlp_protocol'] = os.getenv('OTEL_EXPORTER_OTLP_PROTOCOL') or 'http/protobuf'
        configure_otel_providers(service_name='matchmind-backend', enable_sensitive_data=sensitive,
                                 enable_console_exporters=mode == 'console', **options)
    _configured = mode
    return mode


def shutdown_tracing() -> None:
    """Flush and close exporters at shutdown so the final spans are not lost."""
    if _configured in (None, 'off'):
        return
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    for method in ('force_flush', 'shutdown'):
        if hasattr(provider, method):
            getattr(provider, method)()


@contextmanager
def narrative_span(run_id: str, audience: str, language: str) -> Iterator[Any]:
    """Parent span for one narrative run; framework agent and workflow spans nest under it."""
    try:
        from opentelemetry import trace
    except ImportError:  # base install without the optional SDK
        yield None
        return
    tracer = trace.get_tracer('matchmind')
    with tracer.start_as_current_span('matchmind.narrative_run', attributes={
            'matchmind.run_id': run_id, 'matchmind.audience': audience, 'matchmind.language': language}) as span:
        yield span
