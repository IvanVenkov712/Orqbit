# Implementation roadmap

The current prototype already has PostgreSQL persistence, authentication, permissions, attempts, atomic claims, owned outcomes, migrations, containers, and CI. The [status page](status.md) records current behavior and verification. The broader reliability milestones below include additional work that remains planned.

| Milestone | Current progress |
| --- | --- |
| Identity, authorization, attempts | Implemented foundation; separate process identity and attempt-detail API remain |
| Submission idempotency | Planned |
| Atomic claims and owned acknowledgements | Claims and ownership implemented; acknowledgement replay and leases remain |
| Heartbeats, deadlines, recovery | Planned |
| Retries and complete history API | Attempt records exist; retry scheduling and detailed history routes remain |
| Operations | Compose, readiness, and CI implemented; metrics, resource limits, load tests, and backup/restore remain |

## 1. Identity, authorization, and attempt model

User JWT authentication, hashed worker API keys, authenticated creator attribution, permission policies, supported types, attempt storage, foreign keys, and attempt uniqueness constraints are implemented. Workers are registered credentials rather than independently fenced process instances. Remaining extensions include credential rotation/revocation management and an authorized attempt-detail/history API; job reads currently expose attempt IDs only.

Request validation and limit/offset pagination are implemented. Body size limits and request/job correlation IDs remain. Decide tenant-isolation and operational requirements before a public pilot.

**Verified foundation:** creator identity comes from authentication, unauthorized reads/claims/outcomes are rejected, and attempts retain worker attribution. Separate process-instance fencing and full history access have not been established.

## 2. Idempotent submission

Implement creator-scoped keys, canonical request fingerprints, retention rules, and transactionally coupled job/key insertion. Update the versioned client contract and examples.

**Done when:** simultaneous identical submissions and a retry after a lost response produce one job; key reuse with changed content returns 409; different creators can use the same key independently. No client-facing release should precede this milestone.

## 3. Atomic claims and owned acknowledgements

Oldest-eligible pending claims use `FOR UPDATE SKIP LOCKED` and atomically create an owned running attempt. Success/failure locks the attempt and checks the worker and running status before updating job and attempt together. Concurrent claims and rollback are covered by PostgreSQL tests.

Remaining work includes due-time scheduling, lease metadata/fencing, exact acknowledgement replay, competing outcome-report regression tests, and deliberate API-query timeout policy. Current repeated acknowledgements return 400. Database connection timeouts and readiness statement timeouts already exist.

**Done when:** concurrent claimers never obtain two active attempts for one job; workers cannot finish another worker's attempt; competing success/failure reports resolve to one outcome; accepted acknowledgement retries are safe.

Claim exclusivity and worker ownership checks now pass. Leases are a future extension; a worker crash can still leave a job running permanently. Define their contract before adding automatic expiry processing.

## 4. Heartbeats, deadlines, and crash recovery

Add worker liveness, per-attempt lease renewal, hard attempt deadlines, and the independently runnable recovery process. Make recovery safe across multiple instances. Add graceful worker draining and a minimal example worker that demonstrates the protocol and cooperative lease-loss handling.

**Done when:** killing a worker, dropping its network connection, or restarting API/recovery processes leaves no permanently orphaned job; stale acknowledgements and late heartbeats are rejected. Test heartbeat/expiry races. Recovery latency and oldest expired-lease age are observable.

## 5. Retry policy and complete attempt history

Add retryability classification, maximum attempts, capped backoff with jitter, persisted `available_at`, and optional job deadlines. Close the old attempt and schedule the next execution in one transaction. Provide a failed/exhausted-job listing and history with failure/timeout reasons and durations.

**Done when:** transient failures recover after the configured delay; permanent errors and exhausted budgets stop; restart does not reset retry timing/counts; crashes/timeouts count toward the budget; no prior outcome is overwritten. Demonstrate idempotent external actions in the example worker.

## 6. Operational release gate

Complete metrics, structured logs, dashboards/alerts, rate limits, queue quotas, payload/result retention, backup and restore procedures, credential rotation, and deployment/rollback guidance. Exercise representative load and failure scenarios; tune claim/expiry indexes, pool sizes, polling, and recovery batches from measurements.

**Done when:** the correctness and reliability checks in [requirements](requirements.md) pass; agreed performance/SLO targets are met under a documented workload; a restore drill succeeds; operators can diagnose and recover expired leases and failed jobs using a runbook. Do not defer authentication, CI, basic telemetry, or concurrency tests until this phase; expand the foundations established earlier.

## 7. Add capabilities from demonstrated need

Consider audited manual replay, cancellation, priorities/fairness, scheduled jobs, longer polling, batching, per-tenant concurrency quotas, webhooks, SDKs, and payload storage outside PostgreSQL. Design webhook delivery with its own retry/idempotency model. Consider recurring jobs, workflows/dependencies, and broker integration only after the core reliability model is proven.

These later reliability and operational milestones describe future direction. They do not expand the learning MVP by default; implement a small, explicitly scoped increment with tests when it is needed. Completion is determined by acceptance evidence, not by having endpoint names present.
