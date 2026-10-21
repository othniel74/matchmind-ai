> **Historical document.** It records MatchMind at the date it was written; its test counts, limitations and plans are not current. For the current state see the [README](../README.md) and the [documentation index](README.md).

# MatchMind AI technical implementation and risk controls

> Implementation update (19 October 2026): the local Evidence Lab now includes versioned provenance, deterministic claim checks, local password sessions, analyst/reviewer roles, account-attributed review, controlled local publication and atomic withdrawal on supporting corrections. See [local evidence foundation](LOCAL_EVIDENCE_FOUNDATION.md) for current scope and 79-test verification. Cloud identity, tenant isolation, external delivery and production evaluation remain incomplete.

Production architecture and verification specification

Prepared for the MatchMind product and engineering team. Baseline: 18 October 2026. This document consolidates the implementation plan and the risks behind evidence-backed football storytelling. It complements Product Strategy Version 2 and preserves the earlier architecture and requirements documents.

MatchMind is intended to help producers and match analysts discover, verify and publish useful football stories. The production design combines a shared match context, deterministic analysis, NetworkX, a knowledge graph, constrained AI and editorial approval. The local prototype implements only part of this design. This specification does not establish production readiness or guarantee zero hallucinations.

## How status is reported

Implemented means code exists and the named local checks provide evidence for a bounded capability. Partial means a useful control exists but does not cover the production failure scenario. Planned means design or acceptance requirements only. Unverified means integration code or configuration exists without observed end-to-end service behavior. Proposed owner roles and performance targets below are not assigned commitments or service guarantees.

## Current implementation baseline

| Area | Evidence in the local code | Production boundary |
| --- | --- | --- |
| Match engine | Synthetic validation, deterministic statistics and activity insights in core.py | Activity counts are not proof of tactical pressure or causation |
| Narratives and overlays | Evidence checks, audience and EN/ES variants, timed overlay windows | General sentence support and editorial approval are incomplete |
| NetworkX | Recipient-based passing networks and temporal comparisons | Legacy proxy edges remain labeled; provider-wide validity needs evaluation |
| Knowledge graph | Bolt adapters and mocked transaction tests | Live graph storage, retrieval and correction propagation are unverified |
| AI adapter | Optional sequential roles, timeouts, output filters and fallback | SDK construction is tested; live Foundry execution is unverified |
| Storage and replay | SQLite replay integrity and WebSocket resume | No production tenancy, distributed ordering or operational recovery proof |
| Research sources | SkillCorner tracking, synchronized Metrica excerpt and StatsBomb event analysis | Separate research matches; no licensed live feed or footage |

The latest recorded baseline is 55 backend tests passing across a suite run and a storage-test rerun after temporary-directory setup failures. Frontend builds and targeted tracking and ball-display checks passed locally. This document does not imply that its proposed production tests have run.

<!-- page -->
# Production architecture and match contracts

## One selected match drives all outputs

Provider adapters feed a canonical event log and a versioned match state. Deterministic calculations and NetworkX derive observations from that state. The knowledge graph connects observations to source versions and downstream stories. Evidence retrieval supplies bounded context to AI; validation and producer approval control publication. Replay, overlays and recaps use the same match context.

NetworkX and graph storage are distinct responsibilities. NetworkX computes measurements; the knowledge graph preserves relationships, context and provenance. The event log remains authoritative. Neither graph structure nor a fluent model response makes an unsupported claim true.

## Proposed canonical contracts

| Contract | Required fields and rules |
| --- | --- |
| MatchContext | workspace_id, match_id, provider, period, clock_seconds, state_version, quality_state and capability flags |
| EventVersion | provider event ID, stable internal ID, source version, sequence, event time, received time, payload hash and correction link |
| TrackingFrame | source frame and frequency, period and timestamp, coordinate convention, positions, detection quality and missing values |
| Observation | metric and algorithm version, source state, comparison windows, deterministic result, evidence IDs and limitations |
| EvidencePacket | observation IDs, exact event versions, permitted time window, measurements, provenance and data-quality flags |
| StoryVersion | structured claims, evidence packet ID, audience, language, model and prompt versions, validation and editorial state |
| PublishedOutput | approved story version, target surface, schedule, expiry, publication key and withdrawal or correction history |

These are proposed contracts, not existing API schemas. Current field names and research adapters do not yet implement this unified model.

## Source and timing boundaries

Keep provider IDs scoped by provider and match. Normalize pitch dimensions, attacking direction, periods and clock offsets before analysis. Preserve original coordinates and timestamps for audit. Missing data stays missing; event-only feeds cannot support continuous formation or speed claims. A halftime break, stoppage time or shootout must not be inferred from an absolute minute alone.

The research UI currently separates real-data clocks from the synthetic dashboard and overlays. Production must replace that separation with a shared match selector and context validation at every API, retrieval and publication boundary. Raw data from unrelated matches must never be silently combined.

<!-- page -->
# Knowledge graph implementation

## Foundation from the first stage

The knowledge graph is a core production component. Define its identities, relationships and version semantics alongside the match pipeline, before stories depend on them. Selecting and deploying a database can proceed in stages; evidence relationships cannot be deferred until after publication features are built.

Use the existing GraphRepository abstraction as a starting point. Evaluate Memgraph or Neo4j against actual queries, licensing, deployment and operations. Existing common Cypher support and mocked tests do not establish real database parity or production performance.

## Proposed relationship model

| Entity group | Relationships and constraints |
| --- | --- |
| Match and identity | Match has periods and teams; players participate with match-scoped identity mappings |
| Source history | EventVersion belongs to a match; a correction supersedes an earlier version without erasing audit history |
| Analysis | Observation uses an algorithm version and cites exact event versions and a state snapshot |
| Evidence and narrative | EvidencePacket supports structured claims in a StoryVersion; citations must support the stated relation |
| Editorial and publication | Approval authorizes a specific StoryVersion; PublishedOutput references that version and its schedule |

Store large raw payloads and tracking streams in suitable durable storage, with graph references and hashes. Avoid making the graph the only copy of provider data. Enforce workspace and match scope in both identifiers and queries.

## Queries required by the product

Why this moment matters retrieves the measurements and sequences supporting a candidate story. Ask the match retrieves only authorized facts within the selected clock window. A developing-story timeline records which new evidence strengthens, weakens or invalidates an observation. Recaps retrieve validated moments with their original evidence and approval state.

## Corrections are a dependency workflow

Persist a new source version, identify dependent observations and recompute their measurements. Mark affected story versions and scheduled outputs as requiring review. An approval for one version does not automatically authorize its replacement. Preserve producer decisions and use explicit correction or withdrawal records for published material.

Acceptance requires a corrected pass to identify every dependent artifact in the fixture graph, including scheduled overlays and recaps. Test the real database, interrupted rebuilds, idempotent retries and graph recovery against the canonical log. Do not claim automatic live correction handling until those checks pass.

<!-- page -->
# AI and editorial publication controls

## Current protection and its limits

core.validate_insight recomputes selected activity counts and checks exact evidence membership. narratives.py and overlays.py validate their supported outputs. These controls are useful for their specific schemas; they do not validate every possible football statement.

The optional agents.py workflow supplies validated facts to three sequential roles. Its final checks reject digits, some causal language, empty text and excessive length before substituting generated prose into a deterministic narrative. This is a conservative filter, not semantic proof. An invented player name, a number written in words or an unsupported causal paraphrase could evade it. Live model behavior has not been verified.

## Required publication sequence

1. Calculate factual quantities in deterministic code and freeze the source state for the request.
2. Retrieve a scoped evidence packet from canonical data and the knowledge graph. Do not retrieve future, superseded or unauthorized facts.
3. Ask the model for structured claims with explicit evidence references, separating observation, interpretation and unavailable information.
4. Validate schema, identifiers, source versions, arithmetic, time windows and the actual support for each claim. A valid citation ID alone is insufficient.
5. Reject unsupported factual or causal claims. Use a clearly labeled verified fallback, a qualified draft or no story according to the failure policy.
6. Require producer approval for the specific version, then schedule an idempotent publication with an expiry time.
7. Reassess before publication and after source corrections. Record corrections and withdrawals for already published material.

## Editorial states and human responsibility

Proposed states are candidate, evidence_ready, draft, validation_failed, awaiting_review, approved, scheduled, published, expired, correction_required and withdrawn. Only an approved version with current evidence may transition to publication. A producer edit triggers revalidation; an altered factual claim must not inherit an earlier validation stamp.

## Evidence quality is not model certainty

Show whether data is detected, extrapolated, inferred, missing or corrected. Do not display an invented confidence percentage. Any probabilistic confidence score needs a defined interpretation and calibration against labeled examples. A model's self-reported confidence cannot establish factual accuracy.

<!-- page -->
# Risk register for analytical integrity

All priorities below are provisional assessments for the production design. A partial control is not a closed risk. Each risk must have an assigned owner before a pilot release.

| ID and priority | Failure scenario | Control and current status |
| --- | --- | --- |
| R01 Critical | AI invents an action, player, number or tactical cause | Partial: supported metrics are recomputed and generated prose is filtered. Planned: claim-level support validation, causal restrictions and adversarial evaluation. Fail closed for unverified claims. |
| R02 Critical | A story uses another match, clock interval or source | Partial: research views are labeled separately. Planned: context keys at every boundary, period-aware clocks and rejection of mixed evidence. |
| R03 High | Provider or competition changes reduce detector reliability | Planned: source-specific baselines, schema and distribution checks, labeled evaluation and review of detector applicability. Do not automatically retrain or change thresholds in production. |
| R04 High | A developing story stays active after contrary evidence | Partial: overlays expire. Planned: evidence validity windows, story reassessment and transitions to outdated or correction_required. |
| R05 Critical | A corrected event leaves wrong stories and recaps in use | Partial: replay storage rejects conflicting writes. That is not a correction workflow. Planned: immutable versions, graph dependency queries, recomputation and producer review. |
| R06 High | A true graph measurement is presented as proof of tactics | Partial: proxy and illustrative data labels exist. Planned: minimum evidence windows, sample adequacy checks, alternative explanations and evaluated detector rules. Graph centrality alone cannot prove a cause. |
| R07 High | Missing or extrapolated tracking is treated as exact observation | Partial: research quality labels and missing-position hiding. Planned: capability gates, source-specific quality propagation and suppression of unsupported spatial or speed metrics. |

## Safe analytical behavior

When source context is inconsistent, withhold the story rather than selecting a plausible match. When evidence is insufficient, explain the unavailable capability rather than estimating it without a label. When a detector is out of its validated domain, mark it unavailable or require review; a warning hidden in logs is insufficient.

<!-- page -->
# Risk register for operational delivery

| ID and priority | Failure scenario | Control and current status |
| --- | --- | --- |
| R08 Critical | Provider text or retrieved content injects instructions into AI | Planned: treat source text as data, allowlist tools and retrieval fields, enforce output schemas and test prompt injection. Prompt wording alone is not a security boundary. |
| R09 High | Model, provider or graph service fails or returns late | Partial: optional model calls have timeouts and labeled fallback. Planned: overall deadlines, bounded retries, circuit breakers and tested behavior for each dependency. |
| R10 High | Duplicates, reordering or reconnects cause double publication | Partial: synthetic event validation and replay resume. Planned: idempotency keys, durable cursors, late-event policies, transactional state transitions and publication deduplication. |
| R11 Critical | A user or AI tool reads another workspace's data or publishes without authority | Planned: authentication, scoped authorization, tenant isolation, editorial roles and audit tests. A local exit button is not authentication. |
| R12 High | Latency or AI cost makes the workflow unusable | Partial: local builds and bounded step timeouts. Planned: end-to-end budgets, load benchmarks, quotas, rate limits, caching and cost monitoring. |
| R13 High | Data, footage or character assets are used beyond their permissions | Partial: source notices retained and new research data excluded from release assets. Planned: a rights register and release review covering display, retention, derivatives and redistribution. |
| R14 High | A model, prompt or algorithm update silently changes outputs | Partial: deterministic seeds and replay integrity tests. Planned: versioned artifacts, regression datasets, approval of changes and tested rollback. |

## Safe failure behavior

Continue showing a labeled last-known state only when its age and validity are visible. Stop new publication when required evidence, authority or validation is unavailable. Use a verified deterministic fallback where appropriate; do not represent fallback as live AI. A timed-out draft must not publish after its match window has passed.

The current optional adapter can wait up to 12 seconds for each of three sequential model calls, plus overhead. That is not a verified live-broadcast latency budget. Replace step-only timeouts with an overall request deadline and explicitly test fallback, cancellation and stale-result rejection.

<!-- page -->
# Acceptance tests and evaluation

This is a proposed production acceptance matrix. Existing local test success does not mark these scenarios as passed. Store dated results, fixture versions, execution environment and evidence for each run.

| Test and risks | Required scenario | Acceptance evidence |
| --- | --- | --- |
| A01 R01 R06 | Invented player, unsupported cause, spelled-out number and irrelevant valid citation | Unsafe claim is rejected or withheld; no publication transition occurs; reason is recorded |
| A02 R02 | Overlapping period clocks, another match ID and future events | Correct period and source scope; cross-match and future evidence rejected |
| A03 R03 R07 | Changed schema, missing ball height, extrapolated tracking and unfamiliar source | Capability is labeled or blocked; invalid measurements are not silently produced |
| A04 R04 R05 | Contradictory evidence and a corrected pass supporting several stories | All dependent fixture artifacts are identified; approvals become stale; correction review is required |
| A05 R08 R11 | Malicious event text, unauthorized graph query and cross-workspace identifier | No unauthorized tool execution, data access or publication |
| A06 R09 R10 | Service interruption, duplicate events, reordered delivery and repeated publish request | Deterministic recovery or explicit fallback; no duplicate publication |
| A07 R12 R14 | Recorded load profile, slow model, prompt change and rollback | Latency, costs and regressions measured; late drafts rejected; prior version recoverable |
| A08 R13 | Restricted research data or unapproved asset included in release inputs | Packaging review blocks the release until permission or exclusion is documented |

## Evaluation datasets

Maintain deterministic synthetic fixtures, difficult negative cases, bilingual claim examples, corrected event streams and provider-specific samples whose use is authorized. Include events where no meaningful story should be generated. Prevent evaluation examples from leaking into prompt tuning or test-specific rules without an independent holdout.

Measure factual error, unsupported-claim rate, evidence relevance, abstention behavior, synchronization error, story usefulness and producer editing effort. Report denominators, coverage and failure categories. Human review is required for nuanced tactical interpretation. An additional model can assist evaluation but must not be the only judge of factual correctness.

A pilot gate should require every critical fixture to pass, no observed unauthorized access or duplicate publication in the defined matrix, reviewed unresolved limitations and explicit product approval. These results do not imply that unknown failures are impossible.

<!-- page -->
# Monitoring and incident response

## Separate the kinds of drift

Data drift concerns changes in input schemas, distributions or quality. Detector drift concerns declining usefulness or accuracy against labeled outcomes. Clock drift concerns synchronization across ingestion, replay and display. Story drift concerns an observation becoming outdated as new play develops. Monitor these separately; one generic confidence indicator cannot represent them all.

| Signal | Collection and comparison | Required action and proposed owner |
| --- | --- | --- |
| Schema and identity failures | Rejected events, unknown IDs, missing fields and provider versions | Quarantine invalid records and inspect adapter changes; data engineering |
| Source quality and drift | Missing or extrapolated rates and feature distributions by provider and competition | Compare with a defined baseline; review affected detector availability; analytics |
| Clock and freshness | Event time, received time, state watermark, display time and story age | Suppress stale outputs and surface a freshness warning; platform engineering |
| Claim and retrieval failures | Validation reasons, irrelevant evidence and unsupported statements in sampled review | Investigate model or retrieval versions; AI engineering and editorial lead |
| Publication correctness | Duplicate keys, stale approvals, correction and withdrawal events | Halt affected publication paths and reconcile state; platform and editorial |
| Latency and costs | End-to-end percentiles, queue depth, token usage, retries and per-match spend | Apply quotas or fallback and investigate capacity; platform and AI engineering |

## Thresholds must be based on an agreed profile

Before setting numerical production targets, define event rates, tracking frequency, concurrent matches, users, model and deployment region. Establish a baseline for each provider. Proposed drift thresholds and alert windows need validation against normal match variation; an alert is a review trigger, not proof that the model is wrong.

## Incident workflow

Pause new publication for the affected match or workspace, record the incident context and preserve relevant versions. Establish the last trustworthy state, repair or replay from the canonical log, recompute affected artifacts and request editorial review. Record corrections to outputs already published. Re-enable only after verification and a named release decision.

Logs should use correlation IDs and source references without secrets or unnecessary personal information. Define retention and access policies, alert ownership and an escalation route before a production pilot.

<!-- page -->
# Security and release requirements

## Workspace and editorial boundaries

Add authentication, workspace membership and server-side authorization. Define analyst, producer and administrator permissions around actual actions. Protect graph queries, source exports and publishing endpoints; UI visibility is not authorization. Use least-privilege database and AI identities, environment-based secret management and redacted diagnostics.

Every publication requires an auditable user or approved automation identity. Store actor, timestamp, story version, evidence state and action. Editing an approved draft must invalidate or renew the approval according to policy. Authentication and this workflow are planned; the current local prototype has no production access controls.

## Data and rights boundaries

Maintain a source rights register with permitted environments, display surfaces, retention, derivative outputs, redistribution, expiry and attribution. The StatsBomb integration remains local noncommercial research. Metrica source notices do not establish blanket commercial permission. Tracking access does not grant video or player-likeness rights. Obtain appropriate permissions before a commercial pilot or public release.

For the hackathon, keep synthetic football-realistic data as the core demonstration. Public repository and submission terms require a separate publication review. The official rules retain entrant ownership but grant broad use rights over submissions; review the actual scope before submitting a commercial product. This specification is not a legal clearance or permission to publish.

## Proposed release gates

1. Source and asset permissions are documented for the intended release; restricted research files are excluded.
2. The selected match, clock and evidence versions agree across critical screens and APIs.
3. Critical acceptance fixtures pass and unresolved analytical limits are visible to users.
4. Authentication, workspace isolation and editorial permissions are tested against real storage.
5. Backup, restore, graph rebuild, correction propagation and rollback exercises have recorded results.
6. Live AI claims have observed service traces; fallback is labeled and can be tested deliberately.
7. Latency, capacity, cost and incident ownership are agreed for the pilot profile.

No public release, Azure deployment, paid procurement or submission is authorized merely by writing this plan. Continue local work until those actions are explicitly requested and any necessary permissions are resolved.

<!-- page -->
# Implementation sequence and reference map

## Build complete slices with evidence

| Stage | Implementation work | Exit condition |
| --- | --- | --- |
| 1 Foundations | Canonical match context, versioned source log, graph schema and capability contracts | One match and period model; stable identities; evidence retrieval fixtures |
| 2 Story card | NetworkX observation, graph-backed evidence, structured draft and review state | Claim inspection, source replay and producer edits behave consistently |
| 3 Reliable publication | Approval, scheduling, idempotency, expiry and correction dependencies | Duplicate, stale and corrected outputs pass fault tests |
| 4 AI and personalization | Verified Foundry calls, bounded orchestration, audience and language evaluation | Real traces and semantic support evaluation; safe fallback |
| 5 Questions and recaps | Ask the match, developing-story history and verified recap assembly | Answers and recaps preserve time scope and source versions |
| 6 Production pilot | Authorized source, authenticated workspace, monitoring and recovery | Pilot release gates and user adoption measures reviewed |

## Existing implementation locations

backend/app/core.py implements the synthetic engine and supported insight validation; narratives.py and overlays.py provide deterministic outputs; agents.py contains the optional AI workflow; store.py handles replay persistence; graph/ contains NetworkX and repository code; research.py serves local research datasets.

frontend/src/main.tsx contains workspace and source selection. TrackingReplay.tsx and trackingData.ts handle tracking playback; StatsBombResearch.tsx provides event analysis; HumanPlayers.tsx renders generic players. The proposed contracts are not yet implemented across these modules.

## Proposed implementation locations

Add dedicated match-context, adapter, event-version, evidence, claim, publication and correction modules. Expand the graph repository with scoped queries and migrations. Agree ownership and API contracts before implementation.

## Source documents and maintenance

Read Product Strategy Version 2, GRAPH_INTELLIGENCE_ARCHITECTURE.md, REAL_DATA_SOURCES.md, VERIFICATION_2026_10_17.md and VSCODE_SETUP_AND_TEST_PLAN.md alongside this specification. Dated updates supersede older milestone counts and proxy-edge descriptions; historical verification remains preserved.

Official rules: https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md

Maintain dated code references, test evidence, unresolved risks and operational owners after each slice. Reassess controls when changing provider, model, graph database or deployment profile.

<!-- page -->
# Evaluation protocol and release decisions

Results begin as NOT_RUN. Engineering thresholds are proposed internal choices, not benchmarks, approved service levels or measurements. Product and engineering must approve targets for a named workload before pilot release. Owner roles are proposed and unassigned.

## Evaluation datasets and windows

| Pack | Contents and evaluation boundary |
| --- | --- |
| D1 Deterministic truth | Synthetic fixtures with independently calculated scores, recipients, periods and comparison windows. Run on ingestion, metric or clock changes. Hold out seeds from tuning. |
| D2 Claim and language | Gold facts, support labels, answerable and unanswerable questions, and EN/ES audience variants. Keep tuning and release matches disjoint. Evaluate model, prompt and retrieval changes. |
| D3 Adversarial and faults | Invented identities, irrelevant citations, causal paraphrases, injection, duplicate/late events, corrections, outages and unauthorized workspaces. Run before pilot releases. |
| D4 Load and recovery | Fix match/user concurrency, event/tracking rates, region, model, hardware, duration and fault schedule. Benchmark each workload profile separately. |
| D5 User workflow | Equivalent producer tasks in the current workflow and MatchMind. Counterbalance order; record experience, completion and failures. |

Authorized research samples can supplement appropriate packs, but synthetic performance is not proof of generalization. Do not redistribute restricted source data in evaluation assets. The existing five-seed checks are a baseline consistency check, not a labeled semantic or adoption benchmark.

## Labels and statistical reporting

Use atomic factual claims rather than whole paragraphs as the unit of factual review. Distinguish supported, contradicted, unsupported and unjudgeable claims. Two reviewers should independently label difficult tactical or language examples, with adjudication of disagreement. Record reviewer agreement and excluded cases. This review process is planned.

Report counts, missing observations and source/audience/language slices. Use 95 percent Wilson intervals for independent proportions; cluster-bootstrap repeated claims by match. Bootstrap paired user-task differences by participant. Predeclare resampling settings and sample exclusions. No errors in a small sample does not establish zero production risk.

## Decision policy

A critical deterministic, authorization or publication fixture failure blocks release. Unrun critical fixtures also block release. Advisory metrics require a recorded baseline and an approved target before they can support a release claim. Never record an unavailable denominator or missing measurement as zero or as a pass. Distinguish test-fixture pass rates from observed production error rates.

<!-- page -->
# Factual and narrative quality scorecard

| Metric | Definition dataset window and decision |
| --- | --- |
| Q01 Factual error rate | Contradicted atomic factual claims divided by all reviewable factual claims. D2, per release and by language/audience. Report unsupported and unjudgeable claims separately. Proposed gate: no contradicted claims in the approved publication fixture set; live-rate target needs a baseline and risk review. Owner: AI evaluation lead. |
| Q02 Unsupported claim rate | Claims lacking sufficient support divided by all generated factual claims, measured before and after the publication gate. D2 and D3 on each AI change. Gate: every injected unsupported critical claim must be withheld in D3; no unsupported critical claim may reach publication in that set. Owner: AI evaluation lead. |
| Q03 Evidence support precision | Claim-to-evidence links that actually support the stated claim divided by reviewed links. Existence of a cited ID is not sufficient. D2 each retrieval/model release. Proposed publication-fixture gate: every factual claim has a valid supporting link and correct match/version context. Owner: evidence engineering. |
| Q04 Safe abstention | Report both correct abstentions divided by unanswerable cases, and unnecessary abstentions divided by answerable cases. D2 and D3 each AI change. Gate: all defined unsafe or unavailable critical cases are withheld. Tune the answerable-case target against reviewer-approved usefulness; no single abstention rate is sufficient. Owner: AI evaluation lead. |
| Q05 Detector quality | True candidate stories divided by all candidates gives precision; detected labeled opportunities divided by all labeled opportunities gives recall. D2 by detector, source and time-window size. Define opportunity labels before scoring. Target approval follows a pilot baseline; a high precision score alone cannot hide missed moments. Owner: analytics lead. |
| Q06 Language consistency | Outputs retaining the same approved factual claims and appropriate uncertainty across language variants divided by reviewed variants. Also report bilingual reviewer acceptance for clarity and meaning. D2 each localization change. Gate: no altered critical fact in the release fixtures; clarity targets require review. Owner: localization and editorial leads. |

## Prevent misleading aggregate results

Publish both pre-gate and post-gate rates, with coverage and output volume. A system that suppresses every story could have no published factual errors while being useless. Interpret Q01 to Q06 together with opportunity recall, safe abstention and producer outcomes. Any unjudgeable result needs a reason and must remain visible in the report.

All targets above are proposed fixture requirements. They do not certify semantic correctness in arbitrary matches. New detector, provider or language combinations need their own evaluation coverage before being described as supported.

<!-- page -->
# Timing graph and correction scorecard

| Metric | Definition dataset window and decision |
| --- | --- |
| T01 Match and time integrity | Outputs using the correct workspace, match, period, source state and allowed event-time window divided by outputs checked. D1 and D3 on every context change. Gate: all release fixtures pass; any cross-match or future-event leak blocks release. Owner: data engineering. |
| T02 Overlay alignment | Absolute difference between the scheduled match-clock position and the actual rendered position. Record browser receipt, paint observation, buffering and clock source. D4 per deployment profile; report p50, p95, maximum and lost observations. Proposed p95 target: at most 500 ms, pending profile approval; missed/expired outputs are reported separately. Owner: frontend and platform leads. |
| G01 Evidence trace completeness | Published factual claims resolving to source event versions, algorithm/window, observation, story approval and output record divided by published factual claims. D1/D3 on graph and publishing changes. Gate: every release-fixture claim resolves; missing provenance blocks publication. Owner: graph engineering. |
| G02 Correction coverage | Affected artifacts found divided by all affected artifacts in an independently labeled dependency fixture. Report false invalidations separately. D3 each graph/correction change. Gate: all expected affected observations, drafts, scheduled outputs and recap entries are found. Owner: graph engineering. |
| G03 Correction time | Time from accepted corrected source version to completion of dependency marking and required publication blocking. Separately measure recomputation and human review; do not hide editor time in a machine-latency claim. D4 fault runs. Target must be approved against provider corrections and broadcast policy before pilot. Owner: platform and editorial leads. |
| T03 Duplicate and stale publication | Count duplicate idempotency keys, publications after expiry, and publications using superseded evidence or stale approvals. D3 replay/retry faults before each release; monitor continuously in a pilot. Gate: zero occurrences in the defined fixture runs. Owner: publishing engineering. |

## How to observe timing honestly

Use synchronized server clocks for server spans and monotonic clocks for elapsed durations. Estimate browser/server offset where needed and retain its uncertainty. Do not subtract unrelated clock domains without alignment. A synthetic replay minute advancing every second is not a real-time tracking latency measurement.

Risk coverage: Q01 to Q06 address R01, R03, R06 and R07; T01 to T03 and G01 to G03 address R02, R04, R05, R09 and R10. Passing these measures does not replace authorization or fault-recovery testing.

<!-- page -->
# Reliability security and cost scorecard

| Metric | Definition dataset window and decision |
| --- | --- |
| O01 Processing latency | Time from receipt of a valid event to committed canonical state; separately measure state-to-observation and candidate-to-validated-draft. D4 each material release. Proposed p95 targets: receipt-to-state at most 1 second and candidate-to-draft at most 5 seconds. Profile and approval are pending; these are not verified results. Owner: platform and AI leads. |
| O02 Timely draft completion | Requests yielding a valid draft before the agreed deadline divided by eligible requests; also report error, cancellation, fallback and timeout shares. D4, with a defined model-failure run. Gate: every injected failure follows the specified safe state and late drafts never publish. Success-rate target needs profile approval. Owner: AI engineering. |
| O03 Recovery correctness | Canonical and publication-state discrepancies after restart/replay compared with an independently produced expected state. D3/D4 per persistence or graph change. Gate: zero fixture discrepancies and no lost approvals or duplicate publications. Report restoration duration separately; recovery-time target is pending operational agreement. Owner: platform engineering. |
| O04 Security isolation | Unauthorized read, graph query, export, tool and publication attempts that succeed. D3 permission matrix on every authorization change and pre-pilot release. Gate: zero successes in the defined tests; any bypass blocks release and requires investigation. Owner: security lead. |
| O05 Cost per match and story | Attribute model tokens, retry calls, compute, storage and data charges to a match; divide by valid stories for per-story cost. Report total spend and generated, approved and published story counts separately. D4 and a pilot billing window. A budget must be approved before the pilot; no budget means no cost pass. Owner: product and platform leads. |
| O06 Drift review coverage | Drift alerts with a documented review, disposition and detector/source-version decision divided by actionable alerts. Baseline feature and quality distributions by provider and competition; use a named comparison method and window. Pilot review cadence and thresholds require approval. An alert is not automatic evidence of degraded accuracy. Owner: analytics and data leads. |

## Known gap against the proposed latency budget

The optional adapter currently permits three sequential calls of up to 12 seconds each, plus overhead. That does not establish compliance with the proposed five-second draft target. Overall cancellation, fallback, model selection and orchestration need measurement and redesign before claiming a latency pass.

Specify the D4 workload and target budget in the run manifest before executing a benchmark. Results under a lighter profile cannot be reported as meeting an untested heavier profile. No load, cost, security or drift scores are asserted by this document.

<!-- page -->
# Adoption scorecard and results record

## Proposed pilot protocol

Use D5 with representative broadcast producers and match analysts doing equivalent discovery, evidence-review and publishing tasks. Compare MatchMind with their current workflow, not an invented manual baseline. Record training time, match familiarity, task difficulty, incomplete tasks and reasons for rejection. Counterbalance task order to reduce practice effects. Pilot duration, participant count and success thresholds must be agreed before data collection.

| Metric | Definition window and approval rule |
| --- | --- |
| U01 Story acceptance | Suggestions accepted for use divided by suggestions actually reviewed. Report accepted unchanged, accepted after editing, rejected and unreviewed separately. Measure per session and across the approved pilot window. Improvement target is agreed after the baseline; unreviewed suggestions are not rejected stories. Owner: product and editorial leads. |
| U02 Time to approved story | Time from task start or candidate availability to producer approval, using the same start definition in both workflows. Report paired median differences and uncertainty, completion rate and failed tasks separately. Proposed direction: lower time without worse factual quality; required improvement remains a stakeholder decision. Owner: user research lead. |
| U03 Editing effort | Active editing time and count of substantive factual, contextual and stylistic changes per approved story. Report by language and user role across D5. Do not treat character-edit distance as proof of correctness. Compare with the baseline and agree a target before using it as a release criterion. Owner: editorial lead. |
| U04 Repeat use | Eligible pilot users completing a meaningful review or approval task in a later agreed window divided by eligible users with access and a task opportunity. Define that window and eligibility before measurement. Exclude test accounts and report opportunity limitations. Target depends on the actual match schedule and pilot agreement. Owner: product lead. |

## Results and signoff template

For every metric record: metric ID and definition version; evaluated product/model/prompt/algorithm versions; dataset pack and split; source permissions; load profile; observation window; numerator and denominator; missing and excluded cases; observed value and interval; baseline; approved target; proposed or assigned owner; evidence location; and PASS, FAIL, NOT_RUN or TARGET_PENDING.

Store the initial register in EVALUATION_SCORECARD.csv. Its blank measurements and NOT_RUN states are intentional, not zero results. Do not replace them with estimates. Assign real owners and approve unresolved targets before a production pilot. Record who approved the release and any remaining limitations; a filled spreadsheet alone is not release authorization.

This scorecard adds measurement definitions and proposed decision rules. It does not implement the evaluation harness, collect user outcomes or establish commercial performance. Existing tests remain separate evidence for their bounded capabilities.
