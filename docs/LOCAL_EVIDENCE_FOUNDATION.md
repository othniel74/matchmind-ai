# Local evidence foundation — 19 October 2026

## Current scope

Pitchlight now has a local, single-workspace workflow from versioned synthetic events to evidence-backed drafts, authenticated review and controlled local publication. This is a development milestone. It does not establish production readiness, external broadcast delivery or general hallucination detection.

## Try it

1. Open `/app?view=evidence`, or select **Evidence lab** in the workspace.
2. In **Workspace access**, create your first account using your own username and a password of at least 12 characters. No default accounts or passwords are installed. First-account setup is restricted to loopback and closes once an account exists. The first account is the owner and a reviewer.
3. The owner can create analyst or reviewer accounts. Analysts inspect evidence and correct passes; reviewers also approve/reject drafts and publish to the local feed. Only the owner provisions accounts. Read-only synthetic demo exploration remains available without signing in.
4. Select a synthetic match, team and clock. Inspect the two ten-minute passing windows, source event versions and payload hashes.
5. Provide a review note and approve the draft. The server checks the complete evidence chain and factual template, then records the signed-in account with the decision.
6. Select **Publish to local feed**. The consumer preview serves approved, validated snapshots. No external service receives them.
7. Correct a supporting pass. Observe the invalidated evidence, revoked approval and withdrawn publication. Restore the pass to create a new event version and a fresh draft; approval and publication do not return automatically.
8. Sign out in Evidence Lab, or use **Sign out & exit** in the main workspace. The server invalidates that session.

The actual workspace has been left at first-account setup. Browser-created QA accounts exist only in an isolated test database.

## Configuration

Use `MATCHMIND_CORRECTIONS_ENABLED=true`, `MATCHMIND_REVIEW_ENABLED=true`, and `MATCHMIND_PUBLICATION_ENABLED=true` to enable the respective mutation routes. They are disabled by default; authentication and role checks remain mandatory when enabled. The running local instance enables all three.

Keep the backend bound to `127.0.0.1`. `MATCHMIND_FOUNDATION_DB` overrides the default `backend/data/foundation.sqlite3`. The development host allowlist accepts localhost/loopback plus the test client host; it does not permit arbitrary cloud hostnames. The local origin allowlist covers the development frontend ports 5173/5174 and localhost preview on 8080. Access sessions and publication-feed responses set `Cache-Control: no-store`.

## Implemented controls

- Match context identifies the synthetic seed, source hash, stream, clock and state version. Quality and capability labels explicitly distinguish synthetic events and illustrative animation from real tracking and live AI.
- SQLite retains immutable event versions, SHA-256 payload hashes, correction reasons and actor metadata. Corrections use an atomic transaction, expected-state checks and actor-bound idempotency records.
- Provenance connects EventVersion → Observation → EvidencePacket → StoryVersion → Publication. NetworkX calculates passing networks and traverses observation/draft dependencies. Corrections withdraw dependent publications in the same transaction. Both successful and failed input passes are linked.
- Approval checks the valid evidence chain, complete current input versions, input hash integrity, nonempty evidence, recomputed pass counts and the exact supported deterministic statement. This covers one passing template, not arbitrary natural language. Inconsistent or empty evidence withholds approval. Approval pins the body hash and source state.
- Review decisions retain account identity, body hash, timestamp and note. Pre-authentication decisions remain labeled legacy/unverified and cannot authorize publication; a reviewer can provide a new authenticated attestation.
- Publication requires the exact draft's authenticated approval and successful evidence revalidation. A snapshot captures its body/hash, supporting event-version references, observation, source state, approver and publisher. Snapshot content is retained unchanged when its status becomes withdrawn.
- The authenticated local feed rechecks snapshot hashes, draft approval status and evidence before serving active items. Withdrawn or inconsistent content is excluded. Rejection also withdraws an active publication. Unrelated event corrections leave unaffected publications active.
- Idempotent publication retries return the original immutable creation receipt. That receipt is historical: the local feed is authoritative for whether the item is currently available.
- Synthetic replay, statistics, comparisons, overlays and narrative routes read the corrected source. WebSocket frames include state versions. The workspace clears accumulated output on version changes and withholds mismatched graph/overlay responses. Completed replay views poll for updated state. Evidence/feed previews refresh every three seconds; the access panel refreshes every ten seconds.

## Local account security

Passwords use unique salts and PBKDF2-HMAC-SHA256 with 600,000 iterations. Raw passwords are not persisted. Sessions use random opaque tokens; the database stores their SHA-256 hashes. Cookies are HttpOnly, host-only and SameSite=Strict, with an eight-hour absolute expiry. Secure cookies are used on HTTPS; loopback HTTP remains a local-development accommodation. Session rotation occurs on sign-in, and sign-out deletes the server-side session.

Mutations require a session, a custom local request header, a matching session CSRF token and a trusted origin when supplied. Host validation reduces DNS-rebinding exposure. Login failures are throttled per username/client address after five failures within fifteen minutes. Credential validation diagnostics omit submitted values. Role and actor identity are resolved server-side; request bodies cannot supply an actor or elevate privileges.

Design references: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). These references do not constitute a security audit or certification.

## Validation

**79 backend tests pass; the frontend production build passes.** Tests cover persistent version history, correction/restoration, selective invalidation, unsupported/tampered claims, empty-evidence abstention, authenticated review, role restrictions, owner-only account provisioning, CSRF/origin/host rejection, session expiry/sign-out, password hashing, credential redaction, login throttling, exact publication state/body checks, idempotent receipts, rejection/correction withdrawal, snapshot preservation and fail-closed feed delivery.

Browser verification used a separate local database and frontend: reviewer setup/sign-in, approve → publish → supporting correction → withdrawal, analyst sign-in with approval/publication disabled, and sign-out. The real workspace received no QA account. Existing SDK deprecation warnings and the Three.js bundle-size warning remain. The production evaluation scorecard is still unmeasured; passing functional tests does not fill its drift, hallucination, adoption or latency metrics.

## Remaining production work

Managed cloud identity/MFA, password recovery, account disablement, organization/tenant isolation, stronger administrative role separation, enterprise audit retention and security review remain. The local owner-provisioned account flow is not a production onboarding system. Public demo reads must be revisited before importing private customer data.

There is no external broadcast adapter, delivery acknowledgement, guaranteed downstream cache withdrawal, multi-worker change notification or measured publication SLO. Real-data research views retain separate datasets and clocks. Synthetic player motion remains illustrative. Since this was written, live Foundry inference, typed claim contracts, seven-language validation, Foundry release evaluations and Memgraph/Neo4j parity have been implemented and measured; see the [documentation index](README.md).

Historical milestone counts: 58 tests for the first evidence/correction slice; 68 after local review; 79 after authenticated roles and controlled local publication.
