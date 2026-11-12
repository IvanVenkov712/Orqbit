# Implementation roadmap

This roadmap contains remaining work only. The [status page](status.md) records implemented behavior and verification. These reliability milestones do not expand the learning MVP by default; implement a small, explicitly scoped increment with tests when it is needed.

| Milestone | Current progress |
| --- | --- |
| Identity and access management | Separate process identity, credential rotation/revocation management, and tenant-isolation requirements |
| Coordination hardening | Competing outcome-report regression tests and API-query timeout policy |
| Heartbeats, deadlines, recovery | Worker-process liveness, hard deadlines, draining, and recovery observability |
| Retries and history extensions | Transient-error classification, jitter, retry-exhaustion filtering, timeout reasons, and durations |
| Operations | Metrics, resource limits, load tests, backup/restore, and retention policies |

## 1. Identity and access management

Add separate worker process-instance identity and credential rotation/revocation management. Decide tenant-isolation and operational requirements before a public pilot.

**Done when:** process instances sharing a registered worker credential can be distinguished and fenced, and credential replacement/revocation has an authorized management flow and negative access tests.

## 2. Coordination hardening

Add competing success/failure report regression tests and define a deliberate API-query timeout policy.

**Done when:** overlapping reports resolve to one persisted outcome, exact accepted replays remain safe under contention, and query timeouts have documented response and rollback behavior.

## 3. Heartbeats, deadlines, and crash recovery

Build on the implemented per-attempt leases, authenticated renewal, separate recovery process, and rejection of expired or lost-attempt reports. Add worker-process liveness, process-instance fencing, hard attempt deadlines, and graceful worker draining. Extend resilience demonstrations and recovery observability beyond the current PostgreSQL contention tests.

**Done when:** killing a worker, dropping its network connection, or restarting API/recovery processes leaves no permanently orphaned job; stale acknowledgements and late heartbeats are rejected. Supplement the existing PostgreSQL contention and reassignment tests with live worker-failure and service-restart demonstrations. Recovery latency and oldest expired-lease age are observable.

## 4. Retry policy and history extensions

The current [bounded retry policy](api.md#recovery-and-bounded-retries) already handles lost attempts, saved attempt limits, capped backoff, due-only claims, and atomic retry scheduling with preserved history. Extend it with retryability classification for reported failures, jitter, and optional job deadlines. Add filtering for jobs that exhausted their retry budgets and extend attempt history with timeout reasons and durations.

**Done when:** transient failures recover after the configured delay; permanent errors and exhausted budgets stop; restart does not reset retry timing/counts; crashes/timeouts count toward the budget; no prior outcome is overwritten. Demonstrate idempotent external actions in the example worker.

## 5. Operational release gate

Add metrics, structured logs, request/job correlation IDs, dashboards/alerts, body size and rate limits, queue quotas, payload/result retention, backup and restore procedures, and deployment/rollback guidance. Define submission-key retention and tombstone behavior before adding job deletion. Exercise representative load and failure scenarios; tune claim/expiry indexes, pool sizes, polling, and recovery batches from measurements.

**Done when:** the correctness and reliability checks in [requirements](requirements.md) pass; agreed performance/SLO targets are met under a documented workload; a restore drill succeeds; operators can diagnose and recover expired leases and failed jobs using a runbook.

## 6. Add capabilities from demonstrated need

Consider audited manual replay, cancellation, priorities/fairness, scheduled jobs, longer polling, batching, per-tenant concurrency quotas, webhooks, SDKs, and payload storage outside PostgreSQL. Design webhook delivery with its own retry/idempotency model. Consider recurring jobs, workflows/dependencies, and broker integration only after the core reliability model is proven.

### Potential job-type and submission increments

These ideas span backend contracts, worker registration, and the frontend. They are deferred possibilities, not requirements for the current milestones. Evaluate and implement them as separate increments only when requested:

- **Optional job-type suggestions.** Show a short list of matching names while typing, update it as the input changes, and hide it when no matches exist. Selecting a suggestion is optional. Initially, derive names from workers the user can view; alternatively, add a bounded search endpoint over distinct names in `supported_job_types`, preserving worker visibility checks. Search alone does not require a catalog table. Suggestions do not establish that a worker is online or can claim the submitted job.
- **Explicit job-type catalog.** Defer a `job_types` table containing an internal ID, globally unique name, creator, and parameter schema. Only authenticated users create types through an explicit API operation; worker registration must not create them implicitly. Jobs and worker capabilities reference catalog entries. Reject the entire worker registration if any declared type does not exist; reject submissions with unknown types and validate job parameters against the registered schema. Provide API operations to create, search, and read types. Prefer fixed definitions initially, with incompatible changes receiving a new type name rather than introducing a version-management system. Schema-driven frontend forms remain a separate possible increment.
- **Optional job-type namespaces.** Start with globally unique type names. Consider owner-scoped names such as `ivan/generate_report` only when independent users need to publish different contracts under the same local name. Keep namespace identifiers stable if usernames change. Before introducing namespaces, define ownership and access rules and plan the migration of existing names in job-submission and worker-registration contracts. A separate namespace-management system is not required for the initial catalog.

The catalog is deferred, not a requirement for the current milestones. Before implementation, define type visibility and usage policies and a migration path for existing job and worker type names, including how their schemas will be supplied. Requiring predefined types changes today's worker-registration and submission contracts. Independent workers must not require importing their execution code into the backend.

Additional access-policy controls are already planned in [frontend roadmap step 8](../frontend/docs/roadmap.md#8-remaining-access-policies). The current Private-only control reflects the scope of frontend step 4; the backend already supports the remaining policies.

Completion is determined by acceptance evidence, not by having endpoint names present.
