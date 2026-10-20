"""End-to-end OTLP export: a real exporter sends real protobuf to a local receiver.

The workflow runs in a subprocess because OpenTelemetry providers are process-global.
"""
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest

pytest.importorskip('opentelemetry.exporter.otlp.proto.http')
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

BACKEND = Path(__file__).resolve().parents[1]
CHILD = r'''
import asyncio, os
os.environ['MATCHMIND_SKIP_DOTENV'] = '1'
from opentelemetry import trace
from app.telemetry import configure_tracing
assert configure_tracing() == 'otlp'
from app.agents import FoundryAgentRuntime
from tests.test_agents import fixture, honest, scripted_client
events, insights = fixture()
result = asyncio.run(FoundryAgentRuntime(scripted_client(honest())).run(events, insights, 'broadcast', 'ar'))
trace.get_tracer_provider().force_flush()
print('RUN_ID=' + result.trace.run_id)
'''


def test_spans_reach_a_real_otlp_receiver():
    received: list[bytes] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if self.path == '/v1/traces':
                received.append(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-protobuf')
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = {**os.environ, 'MATCHMIND_TRACING': 'otlp',
               'OTEL_EXPORTER_OTLP_ENDPOINT': f'http://127.0.0.1:{server.server_address[1]}'}
        child = subprocess.run([sys.executable, '-W', 'ignore', '-c', CHILD], cwd=BACKEND, env=env,
                               capture_output=True, text=True, timeout=120)
        assert child.returncode == 0, child.stderr[-2000:]
        run_id = child.stdout.split('RUN_ID=')[1].strip()
    finally:
        server.shutdown()

    spans = []
    for body in received:
        request = ExportTraceServiceRequest.FromString(body)
        for resource in request.resource_spans:
            for scope in resource.scope_spans:
                spans.extend(scope.spans)
    names = [s.name for s in spans]
    root = next(s for s in spans if s.name == 'matchmind.narrative_run')
    attributes = {a.key: a.value.string_value for a in root.attributes}
    assert attributes['matchmind.run_id'] == run_id and attributes['matchmind.language'] == 'ar'
    for agent in ('tactical-analyst', 'match-storyteller', 'audience-editor', 'fact-checker'):
        assert any(agent in name for name in names), names
    assert all(s.trace_id == root.trace_id for s in spans if 'fact-checker' in s.name)
    # No prompt or generated text leaves the process by default.
    assert b'final third' not in b''.join(received) and b'advanced areas' not in b''.join(received)
