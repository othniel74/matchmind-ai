> **17 October 2026 update:** Read [the current verification report](VERIFICATION_2026_10_17.md) before using this earlier plan. Frontend compilation and local browser checks now pass; synthetic scoring, explicit recipients, SQLite replay persistence and WebSocket resume are implemented. Optional SDK imports and client construction are checked with pinned dependencies. Docker/database integration, live Foundry inference and Azure deployment remain pending. The older milestone counts below are historical.

# MatchMind AI — VS Code setup and comprehensive test plan

## 1. Open the project
Use the accompanying ZIP and extract it, **or** run the single-file `MatchMind_AI_All_In_One.py` (Python 3.12+). In VS Code choose **File → Open Folder → matchmind-ai**. Use a terminal at the project root. Prerequisites: Python 3.12+, Node.js 22+, npm, Git, and Docker Desktop (optional until container checks). Never commit real API credentials.

## 2. Backend setup and unit tests
macOS/Linux:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=. python -m pytest -q
PYTHONPATH=. python -m evaluation.run --output ../evaluation-report.json
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Windows PowerShell:
```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PYTHONPATH='.'
python -m pytest -q
python -m evaluation.run --output ../evaluation-report.json
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Check `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/docs`. Verify `GET /api/match`, `/api/events?minute=67`, `/api/state?minute=67`, `/api/insights?minute=67`, `/api/narratives?minute=75&audience=analyst&language=en`, `/api/agents/run?minute=75&audience=fan&language=en`, `/api/overlays?minute=75&audience=broadcast&language=en`. The WebSocket path is `/ws/match?seed=20261020&speed=0.25`. Inspect actual JSON and record errors rather than assuming all endpoints pass.

## 3. Frontend build
```bash
cd frontend
npm install
npm run build
```
To start dev server, use `npm run dev` if provided by `package.json`; otherwise use Docker Compose. Check the frontend Vite proxy and backend availability before testing WebSocket UI. Confirm no TypeScript or runtime errors in browser dev tools.

## 4. Integrated Docker run
From project root:
```bash
docker compose config
docker compose up --build
```
Open `http://localhost:8080`; test match replay, insight selection, Broadcast Studio, audience/language switching, evidence inspection, overlay JSON, and live reconnect. Run `docker compose logs --tail=100` if anything fails. Use `docker compose down` when finished.

## 5. Test matrix — required before submission
| ID | Type | Test | Expected result |
|---|---|---|---|
| T01 | Unit | Repeat identical seed twice | Exact event stream and insight output match |
| T02 | Unit | Different seeds | Valid but different deterministic streams |
| T03 | Unit | Duplicate/out-of-order event | Explicit validation failure |
| T04 | Unit | Invalid coordinates/team/sequence | Explicit validation failure |
| T05 | Unit | Pass distance/accuracy calculations | Match hand-calculated fixtures |
| T06 | Unit | High-pressure synthetic scenario | Shift detected only with threshold met |
| T07 | Unit | Non-shift scenario | No spurious pressure insight |
| T08 | Security | Altered numeric claim | Publication blocked |
| T09 | Security | Fabricated evidence event ID | Publication blocked |
| T10 | Security | Unsupported causal claim | Block or safely qualify |
| T11 | Unit | EN/ES fan/analyst/broadcast | Same validated facts, distinct wording |
| T12 | Unit | Overlay clock/expiry | Correct active/inactive results |
| T13 | Unit | Agent exception/timeout | Safe fallback with explicit trace |
| T14 | Integration | API endpoints | Expected status and JSON schema |
| T15 | Integration | WebSocket replay | Monotonic sequence, no dropped/duplicated updates |
| T16 | Frontend | `npm run build` | Exit 0, no TS errors |
| T17 | Browser | Replay + dashboard | Clock/stats/insights update without JS errors |
| T18 | Browser | Broadcast Studio | Correct overlay preview and evidence IDs |
| T19 | Browser | Language/audience controls | Content changes without altering verified metrics |
| T20 | Browser | Reconnect/refresh | Consistent state and no duplicate overlays |
| T21 | Docker | Compose build/start | Both services healthy and accessible |
| T22 | Foundry | Live SDK authentication/inference | Real model response, explicit provider metadata |
| T23 | Foundry | Agent handoffs/tracing | Observable typed sequence and failure handling |
| T24 | Security | Prompt injection / invented numbers | Gate blocks unsupported outputs |
| T25 | Reliability | Burst events/retries | No double-publication or stale overlays |
| T26 | Performance | p95 event-to-state/insight latency | Meets **proposed** targets under stated load |
| T27 | Accessibility | Keyboard/contrast/screen-reader | Usable critical flows |
| T28 | Cloud | Azure deployed URL | Public demo works without paid login |
| T29 | CI | GitHub Actions on push/PR | Backend, evaluation, frontend all green |
| T30 | Submission | 2-minute video/public repo/licensing | Meets official requirements |

Current automatic suite does not cover every row. Mark each as PASS/FAIL/NOT RUN with dated logs and evidence. For the optional Foundry integration, **never accept deterministic fallback as proof of live AI**.

## 6. Regression and release protocol
1. Run backend tests and offline evaluation after every backend change.
2. Run frontend build after every UI change.
3. Run Docker/browser smoke checks for each candidate release.
4. Capture a real Foundry agent trace with model/deployment details; verify publication gate blocks injected numbers.
5. Run the five seed scenarios plus adversarial and latency tests.
6. Verify public deployment, rights, and submission assets; tag a commit and archive reports.


## Graph tests (M5)

`cd backend && PYTHONPATH=. pytest -q tests/test_graph.py` (7 local tests). Run full suite too. To validate actual databases, use `.env.memgraph.example` and `.env.neo4j.example` as described in `GRAPH_INTELLIGENCE_ARCHITECTURE.md`; test both database rebuilds and readback, not merely health.
