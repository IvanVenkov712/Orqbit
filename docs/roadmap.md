# Implementation roadmap

This roadmap contains remaining work only. The [status page](status.md) records implemented behavior and verification. These reliability milestones do not expand the learning MVP by default; implement a small, explicitly scoped increment with tests when it is needed.

| Milestone | Current progress |
| --- | --- |
| Identity and access management | Separate process identity, credential rotation/revocation management, and tenant-isolation requirements |
| Coordination hardening | Competing outcome-report regression tests and API-query timeout policy |
| Heartbeats, deadlines, recovery | Planned |
| Retries and history extensions | Retry scheduling, retry-exhaustion filtering, timeout reasons, and durations |
| Operations | Metrics, resource limits, load tests, backup/restore, and retention policies |

## 1. Identity and access management

Add separate worker process-instance identity and credential rotation/revocation management. Decide tenant-isolation and operational requirements before a public pilot.

**Done when:** process instances sharing a registered worker credential can be distinguished and fenced, and credential replacement/revocation has an authorized management flow and negative access tests.

## 2. Coordination hardening

Add competing success/failure report regression tests and define a deliberate API-query timeout policy.

**Done when:** overlapping reports resolve to one persisted outcome, exact accepted replays remain safe under contention, and query timeouts have documented response and rollback behavior.

## 3. Heartbeats, deadlines, and crash recovery

Define the lease/fencing contract, then add worker liveness, per-attempt lease renewal, hard attempt deadlines, and an independently runnable recovery process. Make recovery safe across multiple instances. Add graceful worker draining and extend the existing example worker to demonstrate the protocol and cooperative lease-loss handling.

**Done when:** killing a worker, dropping its network connection, or restarting API/recovery processes leaves no permanently orphaned job; stale acknowledgements and late heartbeats are rejected. Test heartbeat/expiry races. Recovery latency and oldest expired-lease age are observable.

## 4. Retry policy and history extensions

Add retryability classification, maximum attempts, capped backoff with jitter, persisted `available_at`, and optional job deadlines. Claims must select only jobs whose scheduled time is due. Close the old attempt and schedule the next execution in one transaction. Add filtering for jobs that exhausted their retry budgets and extend attempt history with timeout reasons and durations.

**Done when:** transient failures recover after the configured delay; permanent errors and exhausted budgets stop; restart does not reset retry timing/counts; crashes/timeouts count toward the budget; no prior outcome is overwritten. Demonstrate idempotent external actions in the example worker.

## 5. Operational release gate

Add metrics, structured logs, request/job correlation IDs, dashboards/alerts, body size and rate limits, queue quotas, payload/result retention, backup and restore procedures, and deployment/rollback guidance. Define submission-key retention and tombstone behavior before adding job deletion. Exercise representative load and failure scenarios; tune claim/expiry indexes, pool sizes, polling, and recovery batches from measurements.

**Done when:** the correctness and reliability checks in [requirements](requirements.md) pass; agreed performance/SLO targets are met under a documented workload; a restore drill succeeds; operators can diagnose and recover expired leases and failed jobs using a runbook.

## 6. Add capabilities from demonstrated need

Consider audited manual replay, cancellation, priorities/fairness, scheduled jobs, longer polling, batching, per-tenant concurrency quotas, webhooks, SDKs, and payload storage outside PostgreSQL. Design webhook delivery with its own retry/idempotency model. Consider recurring jobs, workflows/dependencies, and broker integration only after the core reliability model is proven.

Completion is determined by acceptance evidence, not by having endpoint names present.
