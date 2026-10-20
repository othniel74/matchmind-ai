# MatchMind AI

**Explainable match intelligence from synthetic football events: live, personalized, in seven languages, on Azure and Microsoft Foundry.**

MatchMind turns a stream of football events into what a studio, a broadcaster or a fan actually needs. It finds the key moments and explains why each one matters. It writes recaps and answers questions. It shapes all of this for each viewer and renders it as timed overlays. Every number it publishes is recomputed from the events, and every agent-written sentence passes a fact checker before anyone sees it.

| | |
| --- | --- |
| **Live demo** | https://matchmind-demo.mangograss-8c9a0131.uksouth.azurecontainerapps.io (no sign-in, read-only, synthetic data) |
| **Video (1:44)** | [docs/demo/matchmind-submission.mp4](docs/demo/matchmind-submission.mp4) |
| **MCP server** | `https://matchmind-demo.mangograss-8c9a0131.uksouth.azurecontainerapps.io/mcp` |

All clubs (Calderbrook FC, Merridge Athletic), players and events are fictional and synthetic. MatchMind is not affiliated with the Premier League.

## What it does

The brief's five stages, live:

1. **Ingest.** Match events arrive one at a time through **Azure Event Hubs**: a Container Apps Job publishes the match and the app consumes it. Each event is validated against the stream so far; duplicates are skipped and bad events reported.
2. **Interpret.** Team and player statistics, pass difficulty, ball and shot speed, synthetic speed and distance, control vs chaos, tempo, momentum, and a **match knowledge graph**. The graph holds pass networks for both teams, with hub, key link (betweenness), PageRank and xG chain, mirrored in a Memgraph database.
3. **Explain.** Every moment says why it matters: an opener, an equaliser, "down to ten", a new key link, momentum. **Why?** opens the build-up, the players' network roles before the moment, and the evidence events.
4. **Render.** Timed, machine-readable overlays in Broadcast Studio, ready for a rendering partner, including Arabic right-to-left.
5. **Personalize.** Fan, analyst or broadcast mode; favourite club and players; follow one player; track one metric; 7 languages. The facts stay the same; the selection, emphasis and language change.

On top of the pipeline:

- **Agent-written narratives and recaps.** A Microsoft Agent Framework workflow: insight ranker → tactical analyst → storyteller → audience editor ⇄ **fact checker** → publication gate. If a draft fails the check, verified text is published instead.
- **Ask the match.** A Foundry agent calls MatchMind's own **MCP** tools. Viewers see the tool's verified answer with its evidence, never the model's own text.

## Microsoft and Azure technology

| | Used for |
| --- | --- |
| **Microsoft Foundry** | `gpt-4.1-mini` for every agent; **release evaluations** (groundedness 4.71/5, no unsupported numbers across 21 outputs in 7 languages); **tracing** of agent, model and MCP tool calls. See [FOUNDRY.md](docs/FOUNDRY.md). |
| **Microsoft Agent Framework** | The multi-agent workflow (typed executors, conditional edges, handoffs, retries, fallback) and the MCP-calling Q&A agent. See [AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md). |
| **Model Context Protocol** | 13 read-only match tools served at `/mcp` and over stdio; `.vscode/mcp.json` for GitHub Copilot agent mode. See [MCP.md](docs/MCP.md). |
| **Azure Container Apps** | The API and web app, a Memgraph sidecar, and a Container Apps Job that produces the feed |
| **Azure Event Hubs** | The live match feed, with Entra ID only (SAS disabled). See [EVENT_DRIVEN.md](docs/EVENT_DRIVEN.md). |
| **Application Insights / OpenTelemetry** | Traces, connected to the Foundry project |
| **Azure Container Registry Tasks** | Image builds and real Memgraph and Neo4j integration tests |
| **Managed identity** | Every Azure call (Foundry, Event Hubs, ARM, registry); no keys anywhere |
| **GitHub Actions** | CI on every push: backend tests, the optional-SDK suite, the frontend build |

## Trust by design

- **Claims, not guesses.** Each statistic is a typed claim recomputed from the event log, and tampered numbers are rejected ([CLAIM_CONTRACTS.md](docs/CLAIM_CONTRACTS.md)).
- **Fact checker.** The model extracts statements and code verifies them, in any language. Live: 0 unsafe passes in 264 checks. In the Foundry evaluation, 8 of 21 drafts were blocked and replaced with verified text.
- **Provenance and corrections.** Every output cites its event IDs. A correction reports every moment, claim, overlay and recap it changes.
- **A release gate.** Production mode refuses to start until its controls exist ([PATH_TO_PRODUCTION.md](docs/PATH_TO_PRODUCTION.md)).

## Run it locally

```bash
# backend (Python 3.12)
cd backend
python -m venv .venv-agents && .venv-agents/Scripts/python -m pip install -r requirements-agents.txt
.venv-agents/Scripts/python -m uvicorn app.main:app --port 8000

# frontend (Node 22)
cd frontend && npm ci && npm run dev    # http://localhost:5173
```

Without Azure settings, everything except the model-written text works offline, using verified templates. To use Foundry, copy `backend/.env.example` to `backend/.env`, set the project endpoint and deployment, and run `az login`.

## Tests

- **Backend:** `cd backend && python -m pytest -q`. 247 tests pass with the agent SDK; the core-only suite runs in CI.
- **Real graph databases:** Memgraph and Neo4j parity tests run in Azure ([graph-db-tests.yaml](backend/graph-db-tests.yaml)).
- **Browser:** `cd frontend && npx playwright test` runs the end-to-end tests, including against the live URL ([playwright.remote.config.ts](frontend/playwright.remote.config.ts)).
- **Foundry release evaluation:** `backend/evaluation/foundry_eval.py`.

## Documentation

[Brief coverage](docs/HACKATHON_COVERAGE.md) · [Deployment](docs/DEPLOYMENT.md) · [Agent workflow](docs/AGENT_WORKFLOW.md) · [Foundry](docs/FOUNDRY.md) · [MCP](docs/MCP.md) · [Event-driven feed](docs/EVENT_DRIVEN.md) · [Knowledge graph](docs/GRAPH_INTELLIGENCE_ARCHITECTURE.md) · [Languages](docs/LANGUAGES.md) · [Synthetic simulator](docs/SYNTHETIC_SIMULATOR.md) · [Path to production](docs/PATH_TO_PRODUCTION.md) · [Submission](docs/SUBMISSION.md) · [Build history](docs/HISTORY.md)

## Licence

MIT. See [LICENSE](LICENSE). The Microsoft Rocketbox player models are MIT-licensed and credited separately.
