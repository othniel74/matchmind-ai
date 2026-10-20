# Path to production

MatchMind runs publicly today in **demo mode** on Azure Container Apps. `MATCHMIND_ENV=production` refuses to start, and that is deliberate. It is a **release gate, a safety control**, not a missing feature. A service that publishes match narratives to millions of viewers must not be switched to production by flipping a variable. It goes live when the controls below are in place and verified, and the code enforces that.

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
| **Quality gates** | About 240 backend tests, an offline evaluation, browser tests against the live URL, and CI on every push. |
| **Event-driven ingestion** | Azure Event Hubs carries the match feed. A Container Apps Job publishes it; the API consumes, validates and interprets each event as it arrives; duplicates are skipped and bad events reported. All identity is managed, with no keys. |
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
| 7 | **Release evaluations** | Foundry evaluations (groundedness, relevance, coherence, fluency and the custom fact-check scorer) run on a fixed set before each release, with thresholds in CI | A release fails automatically when a score drops below its threshold |
| 8 | **Reliability targets** | SLOs: insight latency under 2 s at p95 from event to overlay; 99.9% availability; alerts in Azure Monitor; at least 2 replicas across zones | Load and fault tests (a replica kill, a model outage, a database failover) |
| 9 | **Content safety** | Azure AI Content Safety on all generated text, in addition to the fact checker | Red-team prompt set with no unsafe outputs |

## Rollout

1. **Pilot:** one broadcaster in one language, with a human reviewer approving every narrative. The workflow already supports review and approval.
2. **Assisted:** approved templates and claims publish automatically; agent narratives still need review.
3. **Automated:** agent narratives publish automatically once the item 7 evaluations meet their thresholds. Reviewers keep the correction and withdrawal tools.

When items 1–9 pass, the gate in `backend/app/runtime.py` is replaced by a startup check that verifies each control is configured. Production then starts only when all of them are present.
