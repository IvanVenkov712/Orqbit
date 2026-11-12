# Backend roadmap

## 1. API and database failure handling

- Define query timeouts for application operations and test rollback and responses after lock waits or timeouts.
- Define consistent responses for temporary database failures and unexpected storage errors without exposing SQL, credentials, or stack traces.
- Decide whether readiness should detect missing constraints and indexes.

## 2. Worker identity and execution bounds

- Separate worker process instances from registered credentials and reject updates from superseded instances.
- Add authorized API-key rotation and revocation management.
- Add worker-process liveness reporting without extending attempt leases implicitly.
- Define hard attempt runtimes and optional overall job deadlines; prevent heartbeats from extending ownership past those limits.
- Add graceful worker draining with a bounded period for finishing and reporting active work.

## 3. Retry and attempt-history extensions

- Define which worker-reported errors are retryable and add bounded retries for those errors.
- Decide whether backoff needs jitter or configuration beyond the fixed policy.
- Add filtering for jobs whose retry budget is exhausted.
- Add explicit finish times, timeout reasons, and execution durations to attempt history.
- Demonstrate idempotent external actions across attempts using a stable job or business-operation key.

## 4. Observability and operational limits

- Add structured logs, request/job correlation IDs, and metrics for queue age, due jobs, active/expired leases, retries, terminal failures, API latency, database pressure, and recovery lag.
- Monitor recovery-process liveness and alert on stalled expiry processing.
- Define payload/result/error size limits, request-rate limits, queue quotas, and overload responses.
- Size representative workloads, then benchmark and tune claim/expiry indexes, connection pools, polling, and recovery batches.
- Define retention and deletion for jobs, attempts, results, and submission keys, including deduplication tombstones when necessary.
- Add backup, restore, deployment, and migration/rollback runbooks; perform a restore drill.
- Decide tenant-isolation requirements before exposing the service beyond its intended users.

Acceptance criteria and design questions are in [requirements](requirements.md) and [architecture decisions](architecture.md).

## 5. Resilience demonstrations

- Kill workers after claim, after an external effect, and before acknowledgement; verify stored state, retry limits, and side-effect deduplication.
- Lose claim/outcome responses and interrupt network access while work is active.
- Restart API, PostgreSQL, recovery, and worker processes during execution and verify that committed work and schedules survive.
- Exercise multiple live recovery processes and measure expiry lag under backlog.
- Run the complete browser/API/independent-worker flow, including reassignment and rejection of late reports.

## Deferred capabilities

Evaluate these as separate increments when requirements justify them:

- Authorized, audited manual replay with an explicit relationship to the original job.
- Cancellation, priorities/fairness, scheduled or recurring jobs, dependencies, and workflows.
- Longer polling, claim batching, and per-tenant concurrency quotas.
- Completion webhooks with a separate delivery/retry contract, SDKs, and large-payload storage.
- An explicit job-type catalog with creator, parameter schema, visibility/usage rules, and a migration plan for existing job types and worker capabilities.
- Optional job-type namespaces with stable ownership and a migration policy.

Interface work is tracked separately in the [frontend roadmap](../frontend/docs/roadmap.md).
