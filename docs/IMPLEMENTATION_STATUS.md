> **Historical document.** It records Pitchlight at the date it was written; its test counts, limitations and plans are not current. For the current state see the [README](../README.md) and the [documentation index](README.md).

# Update 17 October 2026

See `VERIFICATION_2026_10_17.md` for the current results. Synthetic scoring, explicit generated pass recipients, optional durable SQLite replay storage, local Vite proxy, and frontend compilation are now implemented and verified locally. The graph adapter now replaces a match projection in one transaction, with mocked transaction checks; real Bolt integration remains unverified. Prior dated inventory follows for historical context.

# Pitchlight — Implementation status (15 October 2026)

## Scope and truthfulness
This is a **synthetic football intelligence prototype** and submission foundation, not a production service. All football teams/events are fictional. The README contains an early M1 overview plus subsequent M1–M4 update notes; the latest functionality is described here. Do not present fallback agent text as genuine Microsoft AI output.

## Implemented in source code
| Area | Source | Status / caveat |
|---|---|---|
| Deterministic synthetic match generation | `backend/app/core.py` | Implemented, fixed seeds; simplified event realism |
| Event validation, ordering, coordinates | `backend/app/core.py` | Implemented and unit-tested; not durable ingestion |
| Match state, pass and advanced-area metrics | `backend/app/core.py` | Implemented; 0–0 score placeholder, no goal state |
| Territorial pressure-change insights | `backend/app/core.py` | Implemented, heuristic not causal tactical inference |
| Evidence validation | `backend/app/core.py` | Implemented and tested for selected tampering patterns |
| REST endpoints and match replay WebSocket | `backend/app/main.py` | Implemented; no live end-to-end browser verification |
| Deterministic EN/ES narratives and audience modes | `backend/app/narratives.py` | Implemented; no live LLM required |
| Tactical/storytelling/personalization workflow | `backend/app/agents.py` | Implemented fallback and traces; not proven real Microsoft multi-agent execution |
| Optional Microsoft adapter | `backend/app/agents.py` | Experimental and unverified with Foundry deployment |
| Evidence-verified overlays and expiry | `backend/app/overlays.py` | Implemented; synchronized demo semantics only |
| React live dashboard and Broadcast Studio | `frontend/src/` | Source present; compilation/browser run unverified |
| Offline evaluation | `backend/evaluation/run.py` | 5 synthetic seeds, 40 checks passed locally |
| CI workflow | `.github/workflows/ci.yml` | Source present; remote GitHub Actions run not verified |
| Docker Compose | `docker-compose.yml` | Source present; runtime unverified |

## Verified now
- `cd backend && PYTHONPATH=. python -m pytest -q`: **25 passed** on 15 Oct 2026.
- `cd backend && PYTHONPATH=. python -m evaluation.run --output ../evaluation-report.json`: **40/40 offline checks passed** on 15 Oct 2026.
- No verified Azure deployment, live Foundry inference, browser E2E run, or production performance measurements.

## Gaps and limitations
- Goal detection, accurate scoreboard, directional pitch normalization, possession time and calibrated tracking metrics are not implemented.
- Event store, PostgreSQL, idempotent replay ingestion, authentication/RBAC, tenant isolation, billing and commercial data integrations are not implemented.
- The optional Microsoft Agent Framework adapter is not proven against a real deployed model; agent workflow currently falls back to deterministic output.
- Numeric evidence gate is valuable but not a complete hallucination defense; add adversarial testing, schema checks and robust source attribution.
- Frontend build, WebSocket live replay in browser, and Docker compose must be tested in VS Code environment.

## Project layout
`backend/app` API, engine, narratives, agent workflow and overlays; `backend/tests` tests; `backend/evaluation` synthetic checks; `frontend/src` UI; `docs` handover and release checklist; `.github/workflows` CI; root Docker Compose and evaluation JSON.


## M5 — Graph intelligence extension (15 Oct 2026)

**Implemented and unit/API-tested:** NetworkX temporal proxy passing networks; graph metric and evidence endpoints; shared Bolt graph adapter for Memgraph and Neo4j; Docker profiles and configuration examples; guarded rebuild endpoint. Backend suite: 32 tests passing in this environment.

**Unverified:** live database connectivity and parity, frontend build, browser tests, Microsoft Foundry, Azure deployment. Graph receiver edges are synthetic proxies, not confirmed completed-pass receivers. See `GRAPH_INTELLIGENCE_ARCHITECTURE.md`.
