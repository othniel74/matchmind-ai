"""Optional Microsoft Agent Framework runtime with evidence-constrained publication.

Requires agent-framework-azure-ai and Azure identity in the optional dependencies.
The deterministic fallback remains usable without cloud credentials. The orchestration
itself lives in agent_workflow.py and runs on the Agent Framework workflow runtime.
"""
from __future__ import annotations
import os
import time
import uuid
from typing import Any, Literal
from pydantic import BaseModel, Field
from .core import Event, validate_insight
from .narratives import publish_narratives

class AgentRequest(BaseModel):
    minute: int = Field(67, ge=20, le=90)
    seed: int = Field(20261020, ge=0, le=2147483647)
    audience: Literal['analyst','fan','broadcast'] = 'fan'
    language: str = 'en'

class AgentTrace(BaseModel):
    run_id: str
    engine: str
    steps: list[dict[str, Any]]
    handoffs: list[str] = []
    provider: str | None = None
    # True only when the runtime built the Azure client itself; injected clients are tests or tools.
    live: bool = False
    fallback_reason: str | None = None
    duration_ms: int

class AgentResponse(BaseModel):
    narratives: list[dict[str, Any]]
    trace: AgentTrace

def selected_provider() -> str | None:
    """'azure_openai', 'foundry' or None, from MATCHMIND_AI_PROVIDER or whichever is configured."""
    azure_openai = bool(os.getenv('AZURE_OPENAI_ENDPOINT') and os.getenv('AZURE_OPENAI_DEPLOYMENT'))
    foundry = bool(os.getenv('AZURE_AI_PROJECT_ENDPOINT') and os.getenv('AZURE_AI_MODEL_DEPLOYMENT_NAME'))
    choice = (os.getenv('MATCHMIND_AI_PROVIDER') or '').strip().lower()
    if choice == 'azure_openai':
        return 'azure_openai' if azure_openai else None
    if choice == 'foundry':
        return 'foundry' if foundry else None
    if choice:
        raise RuntimeError('MATCHMIND_AI_PROVIDER must be azure_openai, foundry or blank')
    return 'azure_openai' if azure_openai else 'foundry' if foundry else None


class FoundryAgentRuntime:
    """Runs the narrative workflow; only verified deterministic facts reach the model.

    SDK imports are intentionally lazy so the demo works without Azure credentials.
    The Microsoft Agent Framework API is exercised only when explicitly configured
    or when a chat client is injected.
    """
    def __init__(self, client: Any | None = None):
        self.client = client
        self._owns_client = client is None
        self._credential = None

    def _client(self):
        if self.client is not None:
            return self.client
        provider = selected_provider()
        if provider is None:
            raise RuntimeError('No Azure OpenAI or Foundry model is configured')
        from azure.identity.aio import DefaultAzureCredential
        if provider == 'azure_openai':
            try:
                from agent_framework.openai import OpenAIChatCompletionClient
            except ImportError as exc:
                raise RuntimeError('Install optional Microsoft Agent Framework OpenAI integration') from exc
            key = os.getenv('AZURE_OPENAI_API_KEY')
            if not key:
                # Without a key, sign in with Microsoft Entra ID (az login or managed identity).
                self._credential = DefaultAzureCredential()
            self.client = OpenAIChatCompletionClient(
                model=os.environ['AZURE_OPENAI_DEPLOYMENT'], azure_endpoint=os.environ['AZURE_OPENAI_ENDPOINT'],
                api_version=os.getenv('AZURE_OPENAI_API_VERSION') or '2024-10-21',
                api_key=key or None, credential=self._credential)
            return self.client
        try:
            from agent_framework.foundry import FoundryChatClient
        except ImportError as exc:
            raise RuntimeError('Install optional Microsoft Agent Framework Foundry integration') from exc
        # FoundryChatClient calls the project's model deployment through the Responses API.
        # Agents stay defined in code, next to the checks that police them, so no server-side
        # agent is created (FoundryAgent is for agents pre-built in the Foundry portal).
        self._credential = DefaultAzureCredential()
        self.client = FoundryChatClient(project_endpoint=os.environ['AZURE_AI_PROJECT_ENDPOINT'],
                                        model=os.environ['AZURE_AI_MODEL_DEPLOYMENT_NAME'],
                                        credential=self._credential)
        return self.client

    async def check_text(self, events: list[Event], minute: int, text: str, language: str = 'en') -> dict[str, Any]:
        """Fact-check a viewer's own sentence about the match with the workflow's fact checker."""
        try:
            client = self._client()
            from .agent_workflow import check_claims
            return {'available': True, **await check_claims(client, text, events, minute, language)}
        except Exception as exc:  # no model here, or it failed: say so, never guess
            return {'available': False, 'reason': type(exc).__name__, 'text': text, 'minute': minute,
                    'statements': [], 'publishable': False}
        finally:
            if self._owns_client:
                await self._close()

    async def run(self, events: list[Event], insights: list[dict[str, Any]], audience: str, language: str) -> AgentResponse:
        from .telemetry import narrative_span
        run_id = str(uuid.uuid4())
        with narrative_span(run_id, audience, language) as span:
            result = await self._run(run_id, events, insights, audience, language)
            if span is not None:
                span.set_attribute('matchmind.engine', result.trace.engine)
                span.set_attribute('matchmind.live', result.trace.live)
                span.set_attribute('matchmind.fallback_reason', result.trace.fallback_reason or '')
            return result

    async def run_recap(self, events: list[Event], seed: int, minute: int, language: str,
                        audience: str = 'fan', on_step: Any = None) -> AgentResponse:
        """Agent-written recap, fact-checked against verified results, scorers and claims.
        Falls back to the deterministic recap, which is always returned alongside."""
        from .experience import Profile
        from .recap import build_recap
        from .telemetry import narrative_span
        recap = build_recap(events, seed, minute, Profile(language=language))
        fallback = {'insight_id': f'recap:{minute}', 'kind': 'recap', 'audience': audience, 'language': language,
                    'direction': recap['direction'], 'headline': recap['title'], 'body': recap['text'],
                    'evidence_event_ids': [], 'claim_ids': recap['claim_ids'], 'status': 'approved',
                    'engine': 'deterministic_fallback', 'recap': recap}
        run_id = str(uuid.uuid4())
        with narrative_span(run_id, audience, language):
            listener = run_id if on_step is not None else None

            def job():
                from .agent_workflow import NarrativeJob
                # Live runs give the match researcher Pitchlight's own MCP server; injected clients (tests,
                # tools) run offline and the researcher records that it was skipped.
                url = os.getenv('MATCHMIND_MCP_URL', 'http://127.0.0.1:8000/mcp') if self._owns_client else None
                return NarrativeJob(events, [], audience, language, recap_minute=minute, recap_fallback=fallback,
                                    mcp_url=url, listener=listener)
            gate = {'agent': 'evidence_gate', 'status': 'passed', 'mode': 'recap'}
            if listener is None:
                return await self._execute(run_id, job, [fallback], gate)
            try:
                from .agent_workflow import LISTENERS
            except ImportError:  # base install without the optional SDK: the verified recap, no live steps
                return await self._execute(run_id, job, [fallback], gate)
            LISTENERS[listener] = on_step
            try:
                return await self._execute(run_id, job, [fallback], gate)
            finally:
                LISTENERS.pop(listener, None)

    async def _run(self, run_id: str, events: list[Event], insights: list[dict[str, Any]], audience: str,
                   language: str) -> AgentResponse:
        verified = [i for i in insights if validate_insight(i, events)]
        gate = {'agent': 'evidence_gate', 'status': 'passed', 'verified_insights': len(verified)}
        fallback = [n.model_dump() for n in publish_narratives(events, verified, audience, language)]
        if not verified:
            return AgentResponse(narratives=[], trace=AgentTrace(run_id=run_id, engine='deterministic_fallback',
                                                                 steps=[gate], duration_ms=0))
        def job():
            from .agent_workflow import NarrativeJob
            return NarrativeJob(events, insights, audience, language)
        return await self._execute(run_id, job, fallback, gate)

    async def _execute(self, run_id: str, make_job: Any, fallback: list[dict[str, Any]],
                       gate: dict[str, Any]) -> AgentResponse:
        start = time.perf_counter()
        def response(narratives, engine, steps, reason=None, handoffs=(), provider=None):
            return AgentResponse(narratives=narratives, trace=AgentTrace(
                run_id=run_id, engine=engine, steps=steps, handoffs=list(handoffs), provider=provider,
                live=engine == 'microsoft_agent_framework' and self._owns_client,
                fallback_reason=reason, duration_ms=int((time.perf_counter() - start) * 1000)))
        try:
            client = self._client()
            # The workflow module imports the optional SDK; without it, fall back like any other failure.
            from .agent_workflow import run_workflow
            outcome, handoffs = await run_workflow(client, make_job())
            return response(outcome.narratives, outcome.engine, outcome.steps, outcome.fallback_reason,
                            handoffs, type(client).__name__)
        except Exception as exc:
            # Do not expose provider exceptions or credentials to the API consumer.
            return response(fallback, 'deterministic_fallback',
                            [gate, {'agent': 'publication_gate', 'status': 'fallback'}], type(exc).__name__)
        finally:
            # Request-scoped SDK clients and Azure credentials own async transports.
            if self._owns_client:
                await self._close()

    async def _close(self) -> None:
        """Close the request-scoped client, the HTTP clients it wraps, and the credential.
        FoundryChatClient has no close() of its own; its OpenAI and project clients do."""
        client = self.client
        resources = [client, getattr(client, 'client', None), getattr(client, 'project_client', None), self._credential]
        for resource in resources:
            close = getattr(resource, 'close', None)
            if close is None:
                continue
            try:
                result = close()
                if hasattr(result, '__await__'):
                    await result
            except Exception:
                pass
        self.client = None
        self._credential = None
