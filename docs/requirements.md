# Requirements and missing considerations

These are proposed requirements. No performance or availability target has been measured or committed yet. The [roadmap](roadmap.md) places them in implementation order.

## Functional scope

| ID | Requirement | Acceptance expectation |
| --- | --- | --- |
| F1 | Submit and inspect jobs | Validated type/parameters, durable ID, authenticated creator, status/result lookup |
| F2 | Pull eligible jobs by type | Only permitted types, due jobs only, one active attempt per job |
| F3 | Identify workers and track liveness | Authenticated principal plus unique process instance; worker heartbeat and per-attempt lease |
| F4 | Retry failures and abandoned work | Retryability rules, attempt budget, backoff, crash recovery, hard runtime limits |
| F5 | Persist to PostgreSQL | Versioned migrations, constraints, indexes, transactional state changes |
| F6 | Attribute creators and executors | Immutable creator attribution and a worker recorded for every claimed attempt |
| F7 | Run with Docker Compose | API/PostgreSQL/recovery setup, explicit migrations, health checks, persistent volume |
| F8 | Deduplicate submission and acknowledgements | Defined key scope/window, atomic deduplication, safe outcome replay |
| F9 | Preserve execution history | Ordered attempts with worker, timestamps, status, error/result, and timeout reason |

## Non-functional requirements

| Area | Requirement / proposed target | How to establish it |
| --- | --- | --- |
| Correctness | Zero duplicate active attempts in tested concurrent claims; stale attempts cannot mutate current state | PostgreSQL multi-session contention and heartbeat/expiry race tests |
| Durability | A successful submission is acknowledged only after the job and key are committed | Inject lost responses, process crashes, and DB interruptions around commit |
| Delivery semantics | At-least-once execution within retry/deadline policy; no exactly-once side-effect promise | Kill workers before/after side effects and acknowledgements; verify deduplication examples |
| Recovery | Proposed: expiry is processed within one recovery scan interval plus scheduling/DB delay | Fault-injection test; monitor recovery lag; choose an explicit scan interval |
| Security | Authenticated principals, authorization on every operation, protected transport, revocable credentials, no tokens in logs | Negative access tests, secret/log inspection, deployment configuration review |
| Resource bounds | Bounded payloads/results/errors, page size, claim batches, connection pools, request rates, queue growth | Define limits before pilot; load and rejection tests |
| Performance | Set throughput and p95/p99 submit/claim latency targets after workload sizing | Benchmark with realistic backlog, worker count, type distribution, payload size, and DB capacity |
| Availability | Define an availability SLO and recovery objectives before production | Include API, PostgreSQL, and recovery-process dependencies in failure drills |
| Observability | Queue depth/oldest due age by type, active/expired leases, attempts, retries, terminal failures, API latency, pool pressure, recovery lag | Structured logs and metrics; alerts for stalled queues and inactive recovery |
| Maintainability | Declared dependencies, locked environment, migrations, stable API versions, CI | Clean-checkout install/build and PostgreSQL test runs |
| Data lifecycle | Document job/attempt/key retention and deletion; bound history growth | Scheduled cleanup tests, redaction, retention/tombstone consistency checks |
| Operations | Graceful shutdown, readiness, backups, restore, migration/rollback runbooks | Restart/drain checks and a recorded restore drill |

A sensible initial lease proposal is a 10-second heartbeat and 45-second lease, with a recovery scan every 5 seconds. These are configurable starting points, not service guarantees: workload runtime, clock behavior, network pauses, and database outages must inform final values. Define maximum attempt runtimes by job type.

Do not publish arbitrary throughput or uptime claims. First record expected jobs/second, burst/backlog size, concurrent workers, maximum payload/result size, typical/maximum runtime, acceptable queue delay, retention volume, and acceptable data loss (RPO) and restoration time (RTO).

## Important additions to the original feature list

1. **Safe concurrent claiming and stale-worker fencing.** Heartbeats without ownership tokens and atomic transitions still allow duplicate or conflicting updates.
2. **Completion acknowledgements and read APIs.** Submission and pulling alone do not tell clients whether work completed or expose results and failures.
3. **Hard execution deadlines.** A worker can keep heartbeating while a handler hangs; liveness is not progress.
4. **Authentication and authorization.** A creator/worker ID supplied in JSON is not reliable identity. Decide single-tenant versus multi-tenant scope before committing key/access constraints.
5. **Retry limits, error classification, and dead-letter handling.** Poison jobs must stop consuming capacity. Terminal failure inspection is essential; audited replay can follow.
6. **Side-effect idempotency and producer atomicity.** Job deduplication does not prevent repeated external actions or solve a producer's database/HTTP dual write. Document stable operation keys and when an outbox is needed.
7. **Versioned job payloads and worker compatibility.** Workers of different versions may run simultaneously. Evolve payload schemas deliberately and reject unsupported work safely.
8. **Backpressure and fairness.** Rate limits, queue quotas, polling backoff, and worker concurrency limits prevent overload. Priorities and per-tenant fairness can follow measured demand.
9. **Migrations, backups, and retention.** Compose volumes survive ordinary container replacement but are not backups. Ensure history/key retention windows agree.
10. **Operational visibility and recovery ownership.** Queue age, retries, expiry lag, and readiness matter more than process-up status alone. Someone must own alerts and recovery procedures.

Cancellation, delayed/recurring schedules, job dependencies, webhooks, large-payload object storage, and SDKs are useful extensions, but are not prerequisites for the first reliable independent-job processor. Confirm demand before expanding scope.
