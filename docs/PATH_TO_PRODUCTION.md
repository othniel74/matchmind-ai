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
| **Scaling out (designed, not yet done)** | The demo runs on one replica on purpose. The live feed's state (counts, recent events, moments) is kept in memory, so two replicas would each consume part of the Event Hubs partitions and show split counts. Going beyond one replica takes: (1) feed state in a shared store (Azure Cache for Redis), with every replica rendering from it; (2) the Event Hubs consumer on a Blob checkpoint store, so replicas share partitions and resume after a restart; (3) the model-call cache and visitor limits in the same store; (4) HTTP scaling rules on Container Apps, plus KEDA on the Event Hubs backlog for consumers. Reads are already stateless and cached by `state_version`, so the viewer-facing API scales once the feed state moves. Today one replica (1 vCPU) serves 25 concurrent viewers at about 30 requests/s with 0 errors. |
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
