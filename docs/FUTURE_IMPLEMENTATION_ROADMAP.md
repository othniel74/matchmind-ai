> **Historical document.** It records MatchMind at the date it was written; its test counts, limitations and plans are not current. For the current state see the [README](../README.md) and the [documentation index](README.md).

> **17 October 2026 update:** Read [the current verification report](VERIFICATION_2026_10_17.md) before using this earlier plan. Frontend compilation and local browser checks now pass; synthetic scoring, explicit recipients, SQLite replay persistence and WebSocket resume are implemented. Optional SDK imports and client construction are checked with pinned dependencies. Docker/database integration, live Foundry inference and Azure deployment remain pending. The older milestone counts below are historical.

# MatchMind AI — Future implementation instructions

This document is a build backlog, not a claim that these features exist. Preserve the deterministic source-of-truth and evidence gate throughout.

## P0 — Immediately, in VS Code (blockers)
**F01. Verify full application.** Run frontend `npm install && npm run build`, Docker Compose, and browser smoke tests. Fix any build/TypeScript/CORS/WebSocket problems. Add Playwright smoke tests for live replay, Broadcast Studio, and audience/language switching. Acceptance: clean frontend build and 3 repeatable browser runs with no console errors.

**F02. Implement real Microsoft Foundry inference.** Create an Azure AI Foundry project and model deployment. Install the SDKs in `backend/requirements-agents.txt` into the local environment; confirm the actual installed `agent-framework-azure-ai` API and adjust `backend/app/agents.py` to match. Use Azure Identity with a developer login locally and managed identity in Azure. Set `AZURE_AI_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` via local environment, never source control. Add a health/status endpoint that reports whether the provider is **live**, **unavailable**, or **fallback**. Fail closed for any hackathon mode that claims live AI. Acceptance: recorded live model inference with deployment identifier, latency, request correlation and redacted trace; fallback clearly marked.

**F03. Implement genuine multi-agent orchestration.** Add four distinct typed roles: insight ranking, tactical interpretation, narrative, personalization. Use Microsoft Agent Framework orchestration primitives confirmed against installed SDK; do not call a plain Python function chain a Microsoft multi-agent system. Feed agents only validated event/metric objects, require JSON schemas for output, bounded retries and timeout, and record per-agent spans. Re-run evidence gate after every generated factual claim. Acceptance: observed real handoffs, traces and a blocked fabricated number.

**F04. Azure deploy.** Containerize the actual Foundry dependencies; deploy frontend/backend to Azure Container Apps (or an equivalent Azure-managed service), configure managed identity, secrets, HTTPS, observability and safe free-to-view demo. Keep offline fallback mode for local dev but clearly label it. Acceptance: public working URL and clean three-run end-to-end smoke tests.

**F05. Submission.** Prepare public GitHub repo, clear README, installation steps, synthetic data provenance, evaluation report, <2-minute video, category positioning and IP/license review. Verify dates/rules at official hackathon repo before publishing. Acceptance: complete submission and publicly accessible demo.

## P1 — Improve football intelligence and trust
**F06. Real match-state model.** Implement goals, score, match phases, attacking direction per half, possession start/end/duration, lineups/player identities, accurate pass success, shot outcome and match-clock normalization. Write property-based tests and golden fixture cases. Do not use fabricated scoreboard numbers.

**F07. Calibrated synthetic simulator.** Add scenarios for high press, counterattack, set pieces, red cards and substitutions, each with documented ground truth. Separate simulator scenario labels from agent inputs. Evaluate precision/recall against hidden labels; report confidence intervals and failures.

**F08. Evidence contracts and provenance.** Persist source events and model outputs with schema versions, state versions, stable IDs, content hashes and immutable audit logs. Verify every metric from deterministic source; attach citations to overlays and commentary. Add schema validation and red-team adversarial fixtures.

**F09. Robust streaming.** Add replay-safe ingestion with idempotency keys, watermarks, late/out-of-order event policy, durable event store and WebSocket resume. Ensure overlays do not duplicate or show stale insights after retries. Add soak and chaos tests.

**F10. Broadcast-grade overlays.** Frame-/clock-aligned scheduling, priority/collision handling, localization quality, safe-zone positioning, accessibility, user-selectable overlay density and an external JSON/SDK contract. Test synchronization under simulated latency and replay seeking.

## P2 — Commercialization (after hackathon)
**F11. Enterprise architecture.** PostgreSQL migrations, multi-tenancy, SSO/RBAC, audit and retention policies, metering, billing, SLAs and deployment controls.

**F12. Licensed real-world feeds.** Obtain lawful data and video licenses before integrations. Build provider adapters and reconciliation; never imply rights to Premier League match media or branding.

**F13. Product packaging.** MatchMind Studio, Intelligence, Fan and API; customer discovery with broadcasters/clubs/fan platforms, pricing tests, developer docs, quotas and tenant analytics.

## Suggested development order
1. F01 (full verification) → 2. F02 (live Foundry) → 3. F03 (genuine agents) → 4. F04 (Azure) → 5. F05 (submit); parallelize F06/F07 only if P0 remains on schedule. Prioritize a small real live end-to-end demonstration over broad unverified features.

## Definition of done for every future task
Working code, passing automated tests, integration evidence, updated README/status, no secrets in repo, rollback/fallback behavior and a reproducible demo. If an SDK or service cannot be validated, label it pending instead of claiming completion.


## Graph intelligence extension roadmap

See `GRAPH_INTELLIGENCE_ARCHITECTURE.md` for detailed setup and test matrix. Priorities: authoritative recipient data; graph versioning and migrations; dual-engine integration tests; graph-backed evidence publication; interactive network UI; typed Microsoft agent tools; production access controls, benchmarking and licensing review.
