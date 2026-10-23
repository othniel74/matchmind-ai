# Path to production

Pitchlight runs publicly today in **demo mode** on Azure Container Apps. `MATCHMIND_ENV=production` refuses to start, and that is deliberate. It is a **release gate, a safety control**, not a missing feature. A service that publishes match narratives to millions of viewers must not be switched to production by flipping a variable. It goes live when the controls below are in place and verified, and the code enforces that.

This document lists what is already production-grade, what the gate is waiting for, and the Azure services that close each gap.

## Already in place

| Control | How |
| --- | --- |
| **Nothing unverified is published** | Every number is a typed claim recomputed from the event log (`claims.py`). Agent drafts pass an evidence gate, a fact checker that extracts statements for code to verify, and a publication gate, with a deterministic fallback (`agent_workflow.py`). Live fact-checker scores across 264 checks in 7 languages: 0 unsafe passes. |
| **Provenance** | Every moment, overlay, recap line and Ask answer cites its evidence event IDs. A knowledge graph links events to everything built on them. |
| **Corrections** | Event corrections are versioned with idempotency keys and optimistic concurrency, and each one reports exactly which moments, claims, overlays and recaps change. Approved stories are withdrawn for review. |
| **Identity without secrets** | The app reaches Foundry and the registry through its system-assigned managed identity. No API keys are stored, and the image contains no `.env`. |
| **Least privilege at runtime** | Demo mode forces off writes, research data, graph rebuilds and external ingestion, whatever the environment says. The container runs as non-root. |
| **Cost and abuse control** | Model-backed endpoints are cached per match state and limited per visitor (HTTP 429). MCP tools and graph queries make no model calls. |
| **Observability** | OpenTelemetry traces to Application Insights. Prompts and generated text are not exported unless explicitly enabled. |
| **Graph database** | A Memgraph sidecar holds a replayable copy, re-projected on every source change. Its counts are checked against NetworkX, and the app falls back to NetworkX if it is down. Real Memgraph and Neo4j parity tests run in Azure. |
| **Performance under load** | `tools/load-test.py`: 25 concurrent viewers for 60 s on one replica (1 vCPU), each asking for a random minute, the worst case. Before: 8.3 requests/s, median 1.5 s, 95th percentile 8.8 s. Profiling showed every request regenerated the synthetic match. After caching the stream and the parsed events by `state_version`, which every correction bumps: **31.8 requests/s, median 110 ms, 95th percentile 708 ms, 0 errors** ([validation/load-test.json](validation/load-test.json)). A test proves a correction is never served from a stale cache. |
| **Scaling out** | The app runs on 1 to 3 replicas (Container Apps HTTP scaling at 30 concurrent requests per replica), sharing state through **Azure Managed Redis** (Balanced B0, TLS only, key in a Container Apps secret). One replica leads the Event Hubs feed under a 15-second lease and relays every message and its status; the others serve their viewers from the relay, and the viewer's page reconnects when a replica is removed. The model-call cache, the per-visitor limits and the kickoff locks are shared. Measured live on 23 October 2026: 80 concurrent viewers for 170 s scaled the app from 1 to 3 replicas in about a minute and were served **11,016 requests with 0 errors** ([validation/load-test-scaled.json](validation/load-test-scaled.json)); a live match reported identical counts on every replica; a duplicate kickoff was refused across replicas; and with the leader killed at minute 25 (302 events in), the replacement rebuilt the same match from the Event Hubs log and finished it with **1,079 accepted, 0 rejected, 0 duplicates**. If Redis is unreachable, each replica falls back to its own memory. |
| **Quality gates** | About 285 backend tests, an offline evaluation, browser tests against the live URL, and CI on every push. |
| **Event-driven ingestion** | Azure Event Hubs carries the match feed. A Container Apps Job publishes it; the API consumes, validates and interprets each event as it arrives; duplicates are skipped and bad events reported. All identity is managed, with no keys. |
| **Auto-eventing from video** | Broadcast video becomes validated events through Event Hubs. Each stage is scored against ground truth ([VISION.md](VISION.md)), and favours precision: a false event costs more than a missed one. |
| **Real-data readiness** | A provider adapter (StatsBomb) maps real events into the validated contract; across all 64 matches of the 2022 World Cup, 81,931 events were accepted, 0 were rejected and every score matched the official result. The contract supports periods, stoppage time and extra time ([PROVIDERS.md](PROVIDERS.md)). |
| **Interoperability** | A read-only MCP server exposes the same verified tools to other agents and to Copilot. |

## What the gate is waiting for

Each item states the production design, the Azure service, and how it will be verified.

| # | Gap | Production design | Verified by |
| --- | --- | --- | --- |
| 1 | **User identity** | Microsoft Entra ID through Container Apps authentication (Easy Auth) for studio users, with app roles (`analyst`, `reviewer`, `publisher`) replacing local accounts and MFA enforced by Conditional Access | Role tests against Entra tokens; an anonymous write test must fail |
| 2 | **Tenant isolation** | One workspace per broadcaster, with the tenant ID on every record and query, and row-level security in the database | Cross-tenant read and write tests |
| 3 | **Managed data store** | Azure Database for PostgreSQL Flexible Server replaces SQLite for the event log, versions and provenance; migrations are versioned; point-in-time restore is on | Restore drill to a new server; a migration rollback rehearsal |
| 4 | **Event ingestion at scale** | *Done for one consumer:* match feeds already arrive through Azure Event Hubs, and a consumer validates each event with `StreamValidator` ([EVENT_DRIVEN.md](EVENT_DRIVEN.md)). *Still to do:* Blob checkpointing, state in the managed database, and consumers scaled on backlog through KEDA. | Replay of a full match at 10× speed with zero rejected valid events; no lost events across a consumer restart |
| 5 | **Delivery guarantees** | Overlays and recaps leave through an outbox with acknowledgements and withdrawal messages for downstream renderers | A withdrawn overlay must disappear downstream within the SLO |
| 6 | **Secrets and network** | Key Vault references for any remaining secrets; a private registry and database endpoints; Azure Front Door with WAF in front of the API | Configuration scan; penetration test findings closed |
| 7 | **Release evaluations** | *In place locally:* `evaluation/foundry_eval.py` scores published output with Azure AI Evaluation, logs it to Foundry and exits non-zero below its thresholds ([FOUNDRY.md](FOUNDRY.md)). *Still to do:* run it as a release gate in CI. Foundry evaluations (groundedness, relevance, coherence, fluency and the custom fact-check scorer) run on a fixed set before each release, with thresholds in CI | A release fails automatically when a score drops below its threshold |
| 8 | **Reliability targets** | SLOs: insight latency under 2 s at p95 from event to overlay; 99.9% availability; alerts in Azure Monitor; at least 2 replicas across zones | Load and fault tests (a replica kill, a model outage, a database failover) |
| 10 | **Vision on real broadcast video** | GPU inference (Container Apps serverless GPU or AKS); a detector fine-tuned on broadcast frames; shot-boundary and replay detection; jersey-number recognition from close-ups; confidence thresholds so low-confidence events are held for review, not published | Accuracy on annotated real clips against the synthetic-video scores; latency within the overlay SLO |
| 9 | **Content safety** | Azure AI Content Safety on all generated text, in addition to the fact checker | Red-team prompt set with no unsafe outputs |

## Rollout

1. **Pilot:** one broadcaster in one language, with a human reviewer approving every narrative. The workflow already supports review and approval.
2. **Assisted:** approved templates and claims publish automatically; agent narratives still need review.
3. **Automated:** agent narratives publish automatically once the item 7 evaluations meet their thresholds. Reviewers keep the correction and withdrawal tools.

When items 1–10 pass, the gate in `backend/app/runtime.py` is replaced by a startup check that verifies each control is configured. Production then starts only when all of them are present.
