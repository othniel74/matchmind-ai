# Deployment verification backlog — 19 October 2026

Deployment review is deferred at the user's request while product development continues. This file records work already completed and remaining release checks; it is not a production approval.

Already implemented and tested locally: persistent foundation database path in Docker configuration; correct proxy host forwarding; deterministic SQLite connection cleanup; per-item feed integrity and authenticated approval checks; database readiness and sanitized failures; verified SQLite recovery copies with restored sessions revoked. The backend suite passed 92 tests. Docker/Nginx runtime validation was not run because those executables are absent.

`MATCHMIND_ENV=production` is deliberately release-blocked until the remaining controls are implemented and verified. Local development remains enabled.

Before deployment: managed identity and MFA, tenant isolation and private-data authorization, schema migration/rollback process, encrypted off-host backups and scheduled restore drills, external delivery acknowledgements and withdrawal guarantees, load/fault testing and measured SLOs, complete claim validation and drift evaluation, security/dependency review and container integration checks. The evaluation scorecard remains unmeasured.

Recovery tools (from backend): `python -m app.backup backup --output <new.sqlite3>`, `python -m app.backup verify --source <backup.sqlite3>`, and `python -m app.backup restore-copy --source <backup.sqlite3> --output <new.sqlite3>`. Outputs never overwrite existing files. Restore copies revoke all copied sessions. Backups contain private workspace data and credential hashes; keep them in protected storage. Do not point a running service at a recovery copy without a planned cutover. These tools are local building blocks, not a managed backup service.
