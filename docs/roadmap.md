# Implementation roadmap

This order establishes durable state and ownership before adding automatic re-execution. All milestones below are pending unless the [status snapshot](status.md) explicitly says otherwise. Each milestone includes the non-functional work needed to trust it.

## 1. Reproducible PostgreSQL foundation

Declare the supported Python version, dependencies, and a lock file. Add environment-based settings and validated startup configuration. Implement a Dockerfile and Compose services for PostgreSQL and the API, with a persistent database volume, database health checks, and an explicit migration step. Add the recovery service when its executable exists. Keep development credentials out of production configuration.

Replace SQLite configuration with a PostgreSQL driver and versioned migrations, remove schema creation from import, normalize the status enum, and add UTC timestamps. Establish basic lint/syntax checks and PostgreSQL integration tests in CI immediately.

**Done when:** a clean checkout can follow documented commands to build, migrate, start, create/read a job, and preserve it across container restarts. CI runs against PostgreSQL; the API reports not-ready when its required database/schema is unavailable.

## 2. Identity, authorization, and attempt model

Define authenticated client/worker principals, stable creator attribution, worker process instances, permitted job types, and access rules. A practical MVP can use separately provisioned, revocable service credentials; broader identity-provider integration can follow. Add attempt storage, foreign keys, uniqueness constraints, and a paginated authorized history/read API.

Decide whether tenant isolation is required now. Add request validation, body size limits, pagination, secret redaction, and request/job correlation IDs before a public pilot.

**Done when:** creator identity cannot be forged in a body field; a worker cannot impersonate another instance; unauthorized reads and updates are rejected; persisted attempt records retain worker attribution.

## 3. Idempotent submission

Implement creator-scoped keys, canonical request fingerprints, retention rules, and transactionally coupled job/key insertion. Update the versioned client contract and examples.

**Done when:** simultaneous identical submissions and a retry after a lost response produce one job; key reuse with changed content returns 409; different creators can use the same key independently. No client-facing release should precede this milestone.

## 4. Atomic claims and owned acknowledgements

Implement due-job claims with PostgreSQL row locking, create the attempt/assignment/lease atomically, and return attempt credentials. Add conditional, attempt-scoped success/failure updates and idempotent exact acknowledgement replay. Keep transactions short and configure database connection/statement timeouts.

**Done when:** concurrent claimers never obtain two active attempts for one job; workers cannot finish another worker's attempt; competing success/failure reports resolve to one outcome; accepted acknowledgement retries are safe.

The lease is established here; automatic expiry processing comes next. Do not enable multiple real workers before ownership and concurrency checks pass.

## 5. Heartbeats, deadlines, and crash recovery

Add worker liveness, per-attempt lease renewal, hard attempt deadlines, and the independently runnable recovery process. Make recovery safe across multiple instances. Add graceful worker draining and a minimal example worker that demonstrates the protocol and cooperative lease-loss handling.

**Done when:** killing a worker, dropping its network connection, or restarting API/recovery processes leaves no permanently orphaned job; stale acknowledgements and late heartbeats are rejected. Test heartbeat/expiry races. Recovery latency and oldest expired-lease age are observable.

## 6. Retry policy and complete attempt history

Add retryability classification, maximum attempts, capped backoff with jitter, persisted `available_at`, and optional job deadlines. Close the old attempt and schedule the next execution in one transaction. Provide a failed/exhausted-job listing and history with failure/timeout reasons and durations.

**Done when:** transient failures recover after the configured delay; permanent errors and exhausted budgets stop; restart does not reset retry timing/counts; crashes/timeouts count toward the budget; no prior outcome is overwritten. Demonstrate idempotent external actions in the example worker.

## 7. Operational release gate

Complete metrics, structured logs, dashboards/alerts, rate limits, queue quotas, payload/result retention, backup and restore procedures, credential rotation, and deployment/rollback guidance. Exercise representative load and failure scenarios; tune claim/expiry indexes, pool sizes, polling, and recovery batches from measurements.

**Done when:** the correctness and reliability checks in [requirements](requirements.md) pass; agreed performance/SLO targets are met under a documented workload; a restore drill succeeds; operators can diagnose and recover expired leases and failed jobs using a runbook. Do not defer authentication, CI, basic telemetry, or concurrency tests until this phase; expand the foundations established earlier.

## 8. Add capabilities from demonstrated need

Consider audited manual replay, cancellation, priorities/fairness, scheduled jobs, longer polling, batching, per-tenant concurrency quotas, webhooks, SDKs, and payload storage outside PostgreSQL. Design webhook delivery with its own retry/idempotency model. Consider recurring jobs, workflows/dependencies, and broker integration only after the core reliability model is proven.

The first usable durable MVP includes milestones 1–6 plus the release-gate requirements appropriate to its deployment. Completion is determined by acceptance evidence, not by having endpoint names present.
