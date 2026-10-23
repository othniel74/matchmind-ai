> Build history: the previous README, with product branding updated to Pitchlight. The current overview is the [README](../README.md).

# Pitchlight

## Hackathon build â€” 20 October 2026

**Live demo:** https://pitchlight.mangograss-8c9a0131.uksouth.azurecontainerapps.io (read-only, synthetic data). **Video tour:** `docs/demo/matchmind-demo.webm`.

Pitchlight turns synthetic football events into explainable match intelligence, in one pipeline:

1. **Ingest:** events arrive one at a time over WebSocket or an ingest API, each validated against the stream so far.
2. **Interpret:** team and player statistics, xG, pass difficulty, ball and shot speed, and synthetic speed and distance.
3. **Explain:** key moments say why they matter (opener, equaliser, go-ahead), and control vs chaos, tempo and momentum are measured states.
4. **Render:** timed, machine-readable overlays in Broadcast Studio.
5. **Personalize:**
   - viewing modes: fan, analyst, broadcast
   - a favourite club and favourite players
   - follow-one-player and track-one-metric modes
   - seven languages, including right-to-left Arabic

Every number on screen is checked against source events, and match recaps (half-time, full-time, so far) are built from validated claims. AI-written narratives and recaps run on Microsoft Agent Framework with Azure AI Foundry, and are fact-checked before they publish.

Clubs and players are fictional (Calderbrook FC v Merridge Athletic), and all data is synthetic.

See:
- [brief coverage](HACKATHON_COVERAGE.md)
- [deployment](DEPLOYMENT.md)
- [agent workflow](AGENT_WORKFLOW.md)
- [languages](LANGUAGES.md)
- [MCP server](MCP.md)
- [path to production](PATH_TO_PRODUCTION.md)
- [Microsoft Foundry: models, tracing and release evaluations](FOUNDRY.md)
- [event-driven feed on Azure Event Hubs](EVENT_DRIVEN.md)

Verification: 203 backend tests, 56/56 offline evaluation checks, and Playwright smoke tests both locally and against the deployment. The live fact checker let through 0 wrong statements in 264 scored checks.

## Synthetic simulator update 19 October 2026

The synthetic match generator is now possession-based (`possession-v3`), with about 1,100 events per match. It models:
- halves and kick-offs
- set pieces: throw-ins, goal kicks, corners, free kicks and penalties
- fouls and cards, including sending-offs
- 3â€“5 substitutions per team
- shot xG and time-based possession

Each seed also has a hidden scenario label, used only for evaluation. The default demo match now ends 2â€“3.

Insights now separate fact from interpretation:
- The observed count change is checked exactly against source events and may publish.
- The "possible territorial shift" interpretation carries a calibrated z-score and is always held for human review.

`python -m evaluation.run` reports:
- 56/56 correctness and realism checks passing
- shift interpretations at precision 0.52 and recall 0.10, with about 0.1 false alerts per match, against held-out labels

See [simulator and evaluation](SYNTHETIC_SIMULATOR.md).

Narratives now run as a Microsoft Agent Framework workflow, with typed executors, conditional fallback edges and traced handoffs. See [agent workflow](AGENT_WORKFLOW.md). It runs on the stable SDK (Agent Framework 1.22, `FoundryChatClient`) with OpenTelemetry tracing. A semantic fact checker extracts statements from the final text in any language, and plain code verifies each one against the insight and the [claim contracts](CLAIM_CONTRACTS.md).

Pitchlight supports seven languages: English, Spanish, French, Portuguese (Brazil), German, Italian and Arabic, which is right-to-left ([languages](LANGUAGES.md)).

The fact checker also checks tone against the size of the change.

Live results on 19 October 2026:
- the fact checker got 168/168 correct on a held-out multilingual test set, with no wrong statement let through
- traces arrive complete in Application Insights

Browser smoke tests (`npm run test:e2e`) pass. The backend suite passes 168 tests. Statements below about 360 events, a 1â€“2 score and 40/40 checks are historical.

## Current verified state 18 October 2026

**Additional real datasets are integrated locally:** choose **Metrica - tracking + events** for a synchronized 25 Hz sample with event evidence and source-derived counts, or **StatsBomb - real event analysis** for Argentina v France (2022 final), shot/xG analysis and NetworkX passing networks. These research views use separate matches and clocks. Raw files are kept outside the frontend bundle and excluded from deployment images. See [source terms, import and verification](REAL_DATA_SOURCES.md).

Broadcast Studio now offers **Real tracking · SkillCorner**: a free local two-minute historical excerpt with recorded player/ball positions, play/pause, seeking, speed controls and detected/extrapolated/unavailable labels. This is separate from the synthetic score and insights. See [tracking replay details](REAL_TRACKING_REPLAY.md).

Local frontend build and browser replay now work. Scores are calculated from synthetic shot outcomes, and generated completed passes have explicit same-team recipients. NetworkX uses those recipients; legacy event fixtures without recipients retain a labeled proxy fallback.

Set `MATCHMIND_EVENT_DB` to a writable SQLite file to persist complete replays. The store isolates seeds and generator versions, verifies content hashes, and rejects conflicting writes to an existing replay key. Docker Compose mounts a persistent event volume automatically. This is demo replay storage, not a production ingestion service.

`GET /api/runtime` reports provider configuration and storage mode without claiming live inference. Add `require_live=true` to `/api/agents/run` to reject fallback with HTTP 503. The optional SDK is pinned and its client construction tested locally (50 tests pass with optional dependencies). Install `backend/requirements-agents.txt` or build with `INSTALL_AGENTS=true` to include it; this does not establish live inference. Foundry and Azure hosting remain blocked on renewed Azure authentication and project/model configuration. Docker is not installed on the verification machine; real Memgraph/Neo4j tests remain pending.

Broadcast Studio now uses two free MIT-licensed Microsoft Rocketbox footballers, cloned into 22 independently animated players with textured faces, skin and kits. Player detail offers a full-body view and Face close-up. See [player asset credits and verification](PLAYER_ASSETS.md). This improves real-time realism; it is not a claim of fully photorealistic scans.

Broadcast Studio shows 22 numbered synthetic players, distinct team and goalkeeper kits, an active-player marker, a moving ball and pass cues. Players hold an illustrative 4-3-3 with bounded acceleration and turning. Goalkeepers stay in their own penalty areas and face play. Canonical event coordinates remain separate activity cues; they do not teleport the player models. The shared canvas supports inline, expanded and detached views.

The preview now couples players and ball in one illustrative simulation: dribbling, planted kicks, passes, receiving, support runs, defensive pressure, shots and goalkeeper collections. A high-contrast ball and BALL marker keep possession visible. The default frontend replay runs for roughly 90 seconds. This animation is illustrative football play, not tracking data or a reconstruction of the source events; scores and insights continue to use the canonical synthetic events. See [gameplay verification](GAMEPLAY_PREVIEW.md).

Local Windows startup, in separate terminals:

```powershell
cd backend
$env:MATCHMIND_EVENT_DB = './data/events.sqlite3'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173. Vite proxies to the local backend. See [today's verification report](VERIFICATION_2026_10_17.md). Earlier milestone notes below describe historical limitations and test counts; this section supersedes their statements about scores, generated recipients, persistence and local frontend verification.

---

# Pitchlight â€” M1 Working Prototype

A new synthetic-football intelligence demo built for the Microsoft Premier League Hackathon. It generates deterministic synthetic match events, computes statistics, detects changes in territorial activity, attaches source event IDs, and streams results to a React dashboard.

**Scope:** This is the first M1 prototype, not the finished hackathon entry or a production-ready commercial system. AI agents, Microsoft Foundry, persistence, licensed live feeds, multilingual generation and broadcast-grade overlay scheduling are future milestones. Current insights are deterministic and rule-based. Scores are placeholders (0â€“0), not calculated from goals. Teams and events are fictional.

## Quick start

Requirements: Docker and Docker Compose.

```bash
docker compose up --build
```

Open http://localhost:8080. The 90-minute match is replayed at 0.25 seconds per simulated minute (roughly 23 seconds total). Click **Replay match** to restart. A reproducible high-pressure shift is injected into the synthetic event distribution after minute 58.

## API

- `GET /health`
- `GET /api/match?seed=20261020`
- `GET /api/events?minute=67&seed=20261020`
- `GET /api/insights?minute=67&seed=20261020`
- `WS /ws/match?seed=20261020&speed=0.25`

Swagger docs are available at the backend on port 8000 when running locally outside Compose. The nginx frontend proxies API and WebSocket requests.

## Run tests

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

## Architecture

- `backend/app/core.py`: event schema, deterministic simulator, statistics and pressure detector.
- `backend/app/main.py`: HTTP endpoints and WebSocket stream.
- `frontend/src/main.tsx`: responsive live dashboard and evidence view.
- `frontend/src/style.css`: styling.
- `backend/tests`: reproducibility, stats and evidence tests.

## Limitations and next steps

This generator is intentionally simplified; its positional and team distributions are illustrative rather than calibrated against professional football. The pressure indicator counts advanced-area events, not causal tactical changes. Final-third entry direction needs per-team normalization in a later iteration. Event sourcing, event-time ingestion, possession duration, scoring, player metrics, secure authentication, proper model calibration, and stronger statistical evaluation are not yet implemented. Do not describe this as live Premier League intelligence.

Next: strengthen the simulator and match-state semantics, add PostgreSQL and replay-safe ingestion, then implement Microsoft Agent Framework and Foundry for evidence-constrained narratives.


## M1.2 reliability improvements (15 October 2026)

- Reproducible possession sequences and an away-side advanced activity scenario after minute 58.
- Event-stream validation (duplicates, ordering, teams, pitch coordinates and pass destinations).
- Strict insight verification: numeric claims and cited event IDs are recalculated from the exact source stream.
- Expanded match statistics: mean pass distance and advanced-area event counts.
- `GET /api/state?minute=67&seed=20261020` returns an atomic snapshot for debugging and evaluation.
- 10 backend tests passed in the authoring environment (`python -m pytest -q`).

**Data caveat:** The generator models discrete events, not tracking or timed possession. Its advanced-area event counts are **not** a validated measure of actual possession or tactical causation. The demo scoreboard is intentionally fixed at 0â€“0 because shot-to-goal outcomes are not yet modeled. Full Docker/browser verification and Azure deployment have **not** been performed.

## M2 preparation: evidence-gated narrative API (October 2026)

`GET /api/narratives?minute=75&audience=analyst&language=en` returns a validated,
traceable narrative. `audience` is `analyst`, `fan`, or `broadcast`; `language`
is `en` or `es`. The API rejects unsupported parameters and validates every
insight against its source events before publication. It records explicit
workflow stage names and keeps the same evidence references across audiences.

**Integration status:** this implementation is a deterministic fallback and
an integration contract, **not** Microsoft Agent Framework or Microsoft Foundry.
No Microsoft credentials, Foundry model deployment, or agent SDK is configured.
Replace the stage implementations with real Foundry/Agent Framework agents in
M2, retaining the evidence gate and test suite. Do not represent the fallback
as an LLM-generated or Foundry-powered response in a submission.

Run tests: `cd backend && python -m pytest -q`.
Docker was not available in the build environment; container and browser E2E
verification remain outstanding.

## M2 Agent runtime (experimental Azure adapter)

`GET /api/agents/run?minute=75&audience=fan&language=en` executes an evidence-gated
three-agent sequence (tactical analyst â†’ storyteller â†’ audience editor) after a
deterministic evidence gate. Without Microsoft Foundry credentials or optional SDK,
it returns the tested deterministic fallback with an execution trace.

To attempt the Microsoft-backed runtime, install `backend/requirements-agents.txt`
and set `AZURE_AI_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME`; authenticate
with Azure Identity. **Important:** the Azure Agent Framework adapter has not been
integration-tested against a live Foundry project, and SDK interfaces may need
adjustment to the installed release. The current Dockerfile installs only the base
requirements and therefore runs in deterministic fallback mode by default.

The runtime rejects generated numeric claims and certain unsupported causal claims;
this is a limited safety filter, not a comprehensive hallucination guarantee.
No live Microsoft integration or browser deployment is claimed.

## M3 Broadcast Studio (October 2026)

The Broadcast Studio tab provides a synthetic pitch preview, a selectable queue of evidence-verified overlays, English/Spanish and fan/analyst/broadcast filters, and inspectable JSON payloads.

- `GET /api/overlays?minute=67&audience=broadcast&language=en` returns all validated overlays detected through the requested match minute.
- Append `&active_only=true` to retrieve only overlays active at the requested whole-minute clock instant. Overlay lifetime is 8 seconds, so the demo UI also offers historical queue inspection.
- Overlays are derived from deterministic validated insights and narratives, not generated by a live Foundry model. All data are synthetic.
- Backend suite: 21 tests passing in this build environment. Frontend build and Docker/browser integration have **not** been verified in this environment (npm dependency installation timed out).

Start with `docker compose up --build` on a machine with Docker and internet access; open http://localhost:8080 and select Broadcast Studio. Do not use real Premier League media without rights.

## M4 offline evaluation and submission readiness (October 2026)

- `cd backend && PYTHONPATH=. python -m pytest -q` â€” 25 tests passed in authoring environment.
- `cd backend && PYTHONPATH=. python -m evaluation.run --output ../evaluation-report.json` â€” 40/40 synthetic offline checks passed across five fixed seeds.
- See `docs/RELEASE_CHECKLIST.md` for explicit verified vs unverified submission requirements.
- GitHub Actions runs backend tests and evaluation and uploads the evaluation JSON as a CI artifact; frontend build is a separate job.
- **Not yet verified:** frontend compilation (npm installation timed out), Docker/browser end-to-end run (Docker unavailable), Azure hosting, real Microsoft Agent Framework/Foundry integration. These must be completed before a hackathon submission.

## Consolidated VS Code handover

See `docs/IMPLEMENTATION_STATUS.md`, `docs/VSCODE_SETUP_AND_TEST_PLAN.md`, and `docs/FUTURE_IMPLEMENTATION_ROADMAP.md` for an accurate M1â€“M4 implementation inventory, complete test matrix, and prioritized future work. The all-in-one reconstruction file and full ZIP are equivalent distributions of this source tree.


## Graph intelligence (NetworkX + Memgraph / Neo4j)

NetworkX temporal directed passing graphs and two Bolt graph adapters are included. For setup, API endpoints, known data limitations, backend switching and dual-database tests, read [`docs/GRAPH_INTELLIGENCE_ARCHITECTURE.md`](GRAPH_INTELLIGENCE_ARCHITECTURE.md). Graph endpoints work without a database; persistent graph projection requires Docker and explicit opt-in.

## Landing page entry points

The new cinematic local landing page is served at `/`. Enter the match dashboard at `/app` or go straight to Broadcast Studio at `/app?view=studio`. The landing page includes a backend-driven match snapshot explorer with audience/language switching and an evidence inspector. Artwork and design provenance are recorded in `docs/LANDING_PAGE_DESIGN.md`. No hosting deployment was performed.

