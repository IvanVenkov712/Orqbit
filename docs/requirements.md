# Outstanding acceptance requirements

## Worker coordination and retries

| Remaining requirement | Acceptance evidence to add |
| --- | --- |
| Process-instance identity and credential management | Distinguish processes sharing a registered worker; reject superseded instances and rotated/revoked credentials |
| Worker-process liveness | Detect an inactive process without renewing all of its attempts |
| Hard execution limits | A handler cannot renew past its attempt deadline; timeout classification and retry-budget effects are explicit |
| Retryable worker failures | Transient errors receive bounded delayed retries; permanent errors stop; repeated reports cannot schedule duplicate work |
| Attempt diagnostics | Explicit finish times, timeout reasons, durations, and retry-exhaustion filtering are available to authorized callers |
| Graceful draining | A stopping worker ceases claims, renews active work only within a bounded grace period, and reports or relinquishes work according to the defined contract |
| Idempotent external actions | A worker crash after an external effect does not duplicate that effect when the job is retried |

## Operational acceptance

| Remaining requirement | Acceptance evidence to add |
| --- | --- |
| Live failure recovery | Worker kills, lost responses, network interruptions, and service restarts preserve committed work and bounded retry behavior |
| Recovery visibility | Recovery-process liveness, scan lag, and oldest expired lease are measurable and have alerts and an operator response |
| Query timeouts and failure responses | Lock waits, query timeouts, and database failures have defined responses and leave transactions rolled back |
| Resource limits | Explicit payload/result/error sizes, request rates, queue quotas, and overload behavior are tested |
| Performance targets | Representative throughput and p95/p99 submit/claim latency targets are measured against agreed workload sizes |
| Availability objectives | Define an availability SLO, recovery-point objective, and recovery-time objective; exercise all process and database dependencies |
| Retention and deletion | Job/attempt/result/key retention is explicit; cleanup preserves deduplication for the promised replay window |
| Backup and restore | A recorded restore drill meets the agreed data-loss and recovery-time objectives |
| Deployment and security review | Protected transport, credential/log handling, tenant scope, and deployment/rollback procedures are reviewed for the intended environment |

Before setting performance or availability targets, record jobs per second, burst/backlog size, concurrent workers, payload/result sizes, typical and maximum runtimes, acceptable queue delay, and retention volume.

Implementation order is tracked in the [backend roadmap](roadmap.md). Optional product extensions remain separate from these acceptance requirements.
