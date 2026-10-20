# Update 20 October 2026: match knowledge graph

The sections below 17 October describe the first, events-only projection. Several of their limitations no longer apply: the proxy receiver, non-atomic replacement, and "no database tested". This section is current.

## One graph of all verified intelligence

`backend/app/knowledge.py` builds a typed `networkx.MultiDiGraph` from the corrected event log. It is rebuilt and cached per state version, and it is time-scoped, so a graph at minute *m* holds nothing from minute *m* or later.

| Nodes | Relationships |
| --- | --- |
| Match, Team, Player, Possession, Event, Moment, Claim | HAS_TEAM, PLAYS_FOR, PERFORMED, RECEIVED_BY, IN_POSSESSION, BY_TEAM, NEXT, PASSED_TO, EVIDENCES, INVOLVES, FOR_TEAM, SUPPORTS, FOLLOWS |

On the default match, the full graph has about 1,500 nodes. It holds 1,079 events, 260 possessions, more than 100 moments and 7 claims, and it builds in about 0.1 s.

## What runs on it

| Feature | Query | Endpoint |
| --- | --- | --- |
| Network roles, both teams, named | Pass network read back from RECEIVED_BY/PERFORMED; hub (involvement), key link (betweenness on 1/passes distances), PageRank (power iteration, no numpy), strongest lanes | `GET /api/graph/roles` |
| Network-change moments | Every 10 minutes, a team's key link over the last 15 minutes becomes a `connector` moment. The thresholds are 20+ passes, betweenness ≥ 0.25 and pass share ≥ 25%. | in `/api/experience`, overlays, timeline |
| xG chain / xG build-up | xG of possessions a player took part in; build-up excludes the shooter and final passer | `GET /api/graph/xg-chain` |
| Build-up chains | Possessions ending in a shot or goal, as ordered player chains | `GET /api/graph/buildup` |
| Why this moment | Facts, evidence events, the build-up, involved players' roles in the 15 minutes before, the previous moment | `GET /api/graph/why` |
| Developing story | Moments along FOLLOWS with the running score, rendered in 7 languages | `GET /api/graph/timeline` |
| Correction impact | Event → EVIDENCES/SUPPORTS → moments and claims → overlays and recaps; a correction reports which moments and claims change, appear or disappear | `GET /api/graph/impact`, `knowledge_impact` in correction results |
| Focus player's network role | Pass share, betweenness, PageRank, hub or key link, and top partners, for the match so far and the last 15 minutes | focus card in `/api/experience` |
| Ask the match | The model (or a 7-language keyword router) maps a question to a fixed intent; code answers from the graph, claims and stats, cites evidence and refuses anything else | `GET /api/ask` |

The model never writes an Ask answer. It only chooses the intent, and an intent outside the contract falls back to the keyword router.

## Graph database projection

`BoltGraphRepository.project_knowledge` writes the same graph to Memgraph or Neo4j. All nodes carry the label `:KG` plus their kind, and labels and relationship types come from fixed whitelists. Nested values are stored as JSON text. Each match is replaced atomically in one transaction, so a replay is idempotent and other matches are untouched. The older events-only projection (`upsert_events`) is kept, and it no longer deletes knowledge-graph nodes.

The database is queried in Cypher for:
- counts by label and type
- pass lanes in a time window
- moment evidence
- correction impact
- xG chain
- timeline order

`app/graph/projection.py` keeps the database current. It projects at startup, retrying while a sidecar starts, and re-projects when the source's state version changes after a correction. When the database is down, it waits 30 s between attempts and the product keeps running on NetworkX. `/api/graph/knowledge` reports the backend, the projected state version, and whether the database counts match NetworkX. `/api/graph/why` and `/api/graph/impact` answer from the database when it is current and say which source they used.

## Tested against real databases

`tests/test_graph_db.py` runs against running Memgraph 3.13.1 and Neo4j 5.26.32 (community). It checks that both match NetworkX exactly on:
- counts
- pass lanes for whole-match and 15-minute windows
- evidence for 40 moments
- impact for goals and 50 other events
- xG chain
- timeline order

It also checks three more things: replays are idempotent, a corrected projection replaces the old one without touching another match, and the events-only projection leaves the knowledge graph intact.

Docker is not needed locally. The suite runs in Azure Container Registry Tasks (`backend/graph-db-tests.yaml`), with both databases as detached containers on the task network:

```bash
# staging dir = copies of backend/app, backend/tests, backend/requirements.txt,
# backend/Dockerfile.graphtest and backend/graph-db-tests.yaml (nothing else, no .env)
az acr run -r ca7835cfc7a5acr -f graph-db-tests.yaml <staging dir>
```

Run `db4` on 20 October 2026 passed 56 tests with 0 skipped. That covers 9 database tests on each engine, plus the NetworkX graph and knowledge tests. Locally the database tests are skipped unless `GRAPH_TEST_TARGETS` is set.

## In the deployed demo

Memgraph runs as a sidecar container in the `matchmind-demo` Container App, with 0.5 vCPU, 1 GiB and a 768 MiB memory limit. The app reaches it at `bolt://localhost:7687`, and it is not exposed outside the app. It holds a replayable copy, so a restart only re-projects. Graph rebuild over the API stays disabled in demo mode.

## Limits

- The data is synthetic, and pass recipients are generated with it rather than observed.
- Network roles describe passing structure, not tactics or formations.
- The database copy is full-match. Time-scoped answers before minute 90 come from NetworkX, which is the same graph cut at that minute.
- Ask answers a fixed set of question types only.

# Update 17 October 2026

Generated successful passes now contain `recipient_player_id`, and NetworkX uses it even for a terminal pass with no next event. `receiver_method=explicit_recipient` identifies these networks. Legacy streams without recipients retain a next-actor fallback, labeled `mixed_recipient_proxy`. All recipients remain synthetic, not real match observations.

The Bolt adapter now replaces all nodes belonging to the requested match and their edges inside one transaction, then reconstructs the complete projection including recipient-only players. Call `upsert_events` with a complete replay, never an incremental fragment. Existing relationship naming `PROXY_PASSED_TO` is retained for compatibility; consult `receiver_method` for semantics. Sequential replacement avoids obsolete seed projections; concurrent writes, backend compatibility and rollback still require real database integration checks.

Local frontend build and browser checks now pass; no Memgraph or Neo4j instance was available. Earlier design notes below describe the original implementation. Their missing-recipient and non-atomic replacement limitations are superseded by this update.

# MatchMind AI — NetworkX + Portable Knowledge Graph

## Status and architectural contract

Implemented: NetworkX directed, weighted **proxy** passing graphs, centrality, connected components, temporal comparisons; Memgraph and Neo4j using a common Bolt/Cypher adapter; idempotent event and projection upserts; optional rebuild API; API endpoints; unit/API tests.

**Critical data limitation:** the simulator records an event actor, not an actual pass receiver. A successful pass is linked to the *next event actor* only when the next event is on the same team and possession. This is an inferred proxy and must NEVER be presented as observed receiver truth. For commercial feeds, add `recipient_player_id` and use actual completed-pass recipient. Event-based network metrics are not spatial tracking data, formation identification or causal tactical proof.

## Flow

Canonical synthetic events → deterministic match engine → NetworkX analytics → evidence-bearing graph snapshots → optional Bolt graph projection (Memgraph or Neo4j) → API → tactical agents and visualization (future).

The canonical event stream, not the graph, is the source of truth. `GraphRepository` hides database operations from the application. Both databases support the subset of Cypher used in `backend/app/graph/repository.py`; MAGE and Neo4j GDS procedures must be added in *separate backend-specific adapters*.

## Graph model

- `(:Match {id})-[:HAS_TEAM]->(:Team {id,match_id})`
- `(:Team)-[:HAS_PLAYER]->(:Player {id,match_id})`
- `(:Match)-[:HAS_EVENT]->(:MatchEvent {id,match_id,sequence,minute,...})`
- `(:Player)-[:PERFORMED]->(:MatchEvent)`
- `(:Player)-[:PROXY_PASSED_TO {match_id,team_id,weight,event_ids,receiver_method}]->(:Player)`

All player IDs are scoped by match. Graph projection upserts use MERGE; the caller should replay a full match when rebuilding. **Known limitation:** a replay with a *different* seed but the same demo match ID can leave obsolete events or relationships. Do not use rebuild for replacing match data until atomic versioning/deletion has been implemented.

## Endpoints

- `GET /api/graph/network?team=away&minute=67&window=10` — deterministic graph snapshot
- `GET /api/graph/compare?team=away&minute=67&window=10` — prior/current window metrics
- `GET /api/graph/health` — optional graph DB health (503 when unavailable)
- `POST /api/graph/rebuild?seed=20261020` — development-only database projection; requires `GRAPH_REBUILD_ENABLED=true`

The analytical endpoints work even if the database is offline. Database writes are opt-in, not performed automatically during the simulation. Graph rebuild is **not authenticated** and must be disabled in public environments; never enable it on a publicly accessible service.

## Switch backend in VS Code

From project root, choose ONE profile. Docker is required for database integration:

```bash
cp .env.memgraph.example .env
# or: cp .env.neo4j.example .env
```

For Memgraph:

```bash
docker compose --profile memgraph up --build -d
```

For Neo4j:

```bash
docker compose --profile neo4j up --build -d
```

**Important:** If using Neo4j, `.env.neo4j.example` sets `GRAPH_URI=bolt://neo4j:7687` for container-to-container traffic. Memgraph uses `bolt://memgraph:7687`. Neo4j host Bolt is published on 7688; Memgraph host Bolt on 7687. Never start both profiles simultaneously using conflicting backend settings. Set secure credentials before exposing anything outside local development.

```bash
# optional: rebuild the graph once from the demo seed
curl -X POST 'http://localhost:8080/api/graph/rebuild?seed=20261020'
# check DB health
curl http://localhost:8080/api/graph/health
```

The frontend reverse proxy routes `/api` to the backend. Database credentials and graph ports should not be exposed publicly.

## Required verification

1. `cd backend && python -m pip install -r requirements.txt && PYTHONPATH=. pytest -q`
2. `PYTHONPATH=. python -m evaluation.run --output ../evaluation-report.json`
3. `cd ../frontend && npm install && npm run build`
4. `docker compose --profile memgraph up --build -d`, check `/api/graph/health`, rebuild, then inspect event counts and proxy edges.
5. Stop the Memgraph stack. Start Neo4j with `.env.neo4j.example`; repeat identical seeded replay and compare readback.
6. Verify retries and duplicate upserts do not multiply graph nodes or edges; inspect failures/restarts.
7. Confirm no graph-derived insight is published without its event IDs and validation.
8. Security test: graph rebuild endpoint returns 403 by default.

**Not yet verified:** live Memgraph/Neo4j containers, Bolt read/write parity, frontend build/browser, Azure and Microsoft Foundry. Do not interpret the unit tests as database integration tests.

## Future engineering instructions

P0: Add real receiver IDs to synthetic events and validate them against possession state; remove the proxy disclaimer only when supported by the event schema. Add transactional graph versioning, constraints/indexes per backend, incremental replay, and a dedicated authenticated ingestion worker. Add live DB integration tests in CI using disposable Memgraph and Neo4j containers.

P1: Implement evidence-gated graph insight candidates, graph visualizations (passing network with player and evidence drilldown), and typed graph tools for Microsoft Agent Framework. Test that AI never invents players, metrics, or event IDs.

P2: Introduce graph histories across matches, team/competition scopes, tenant isolation, graph query performance benchmarks, recovery/backup procedures, license and compliance review, and a commercial data-provider adapter. Consider MAGE for Memgraph and GDS for Neo4j behind optional capability interfaces.

Memgraph licensing: do not assume its Community Edition is OSI open source; verify current license and commercial rights with legal review before distributing or offering managed services.
