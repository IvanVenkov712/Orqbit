# Open architecture decisions

## Process identity and credential lifecycle

- Define how a worker process obtains its instance identity and how replacement instances invalidate earlier ones.
- Decide whether per-attempt tokens are needed in addition to instance identity, and define their transport, storage, and redaction rules if adopted.
- Define authorized credential rotation/revocation without treating a registered worker ID or caller-supplied name as process identity.
- Set tenant boundaries and credential-management permissions before a public deployment.

## Hard deadlines and draining

- Choose per-type or per-job maximum attempt runtimes and decide whether an overall job deadline is needed.
- Define the interaction between deadlines, heartbeats, retry scheduling, and exhausted budgets.
- Choose how to represent deadline failures and distinguish them from lost ownership in attempt history.
- Define worker-process liveness independently from attempt renewal.
- Set shutdown/draining grace periods and decide how unfinished work is relinquished.

## Retryable failures and manual replay

- Define a public classification for retryable worker errors and which failures remain terminal.
- Decide which retry-policy values should be configurable and saved per job, including jitter and deadlines.
- Define how caller-visible final errors summarize multiple attempts without changing earlier outcomes.
- Specify authorization, audit, idempotency, and budget semantics for manual replay; decide whether replay creates a new linked job.

## Data lifecycle and API evolution

- Define job, attempt, result, and submission-key retention windows together.
- Decide whether deduplication tombstones must outlive deleted job details and when key reuse becomes valid again.
- Define payload/schema compatibility before introducing a job-type catalog or namespaces.
- Decide whether stable public contracts require versioned routes, cursor pagination, or revised response/error conventions. Plan compatibility before changing clients or workers.
- Specify cancellation and webhook delivery contracts only when those features are selected.

## Operational policies

- Define application query timeouts, lock-wait handling, and temporary database-error responses.
- Choose recovery health signals and lag thresholds, and decide whether to expose them through a dedicated check or monitoring.
- Set payload, queue, rate, and concurrency limits from an explicit workload model.
- Use representative PostgreSQL query plans to choose further indexes and tune queue ordering, pooling, polling, and recovery batches.
- Define backup/restore and migration/rollback procedures with acceptable downtime and data-loss objectives.

## External effects and producer atomicity

- Choose stable operation keys for deduplicating external actions across attempts and demonstrate crash behavior around those actions.
- For integrations that both change a producer database and submit a job, decide whether that producer needs an outbox or another explicit atomicity mechanism.
- Define downstream fencing only where the external service supports it and the workload requires it.

Track implementation in the [backend roadmap](roadmap.md) and acceptance evidence in [outstanding requirements](requirements.md).
