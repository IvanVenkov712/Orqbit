# Implementation status

Reviewed on **2026-11-09** against the current working tree. This page includes the pending runtime fixes as well as the committed prototype. Verification of a specific GitHub commit is recorded separately below.

## Feature inventory

| Area | Current behavior | Evidence |
| --- | --- | --- |
| User identity | Registration, Argon2 password hashing, JWT login, and active-user checks | `src/api/routers/auth_router.py`, `src/services/user_auth.py` |
| Worker identity | User-owned workers; generated API keys stored as SHA-256 hashes; active-worker checks | `src/api/routers/worker_router.py`, `src/services/worker_auth.py` |
| Job submission | Authenticated creator, nonblank type, JSON-object parameters, explicit permission policy, pending status | `src/api/routers/job_router.py`, `src/dto/job.py` |
| Reads and lists | Permission-aware job/worker lookup; filtered lists ordered by descending ID with limit/offset pagination | Job and worker routers |
| Claims | Oldest accessible compatible pending job by ID; PostgreSQL `FOR UPDATE SKIP LOCKED`; job update and attempt insert commit together | `src/api/routers/claim_router.py` |
| Outcomes | Owning worker reports by attempt ID; attempt row is locked and must be running; job and attempt update together | Claim router |
| Attempts | Worker attribution, parameters, status, result/error, and UTC creation/update timestamps; job responses expose attempt IDs | `src/models/job_attempts.py`, `src/dto/job.py` |
| Persistence | PostgreSQL with JSONB, synchronous SQLAlchemy sessions, Alembic migrations, and constraints allowing at most one running attempt per job | Models, `src/database.py`, `migrations/` |
| Input errors | Pydantic validation and generic 422 responses for PostgreSQL data errors, including oversized IDs and null characters | DTOs, `src/main.py` |
| Health | Liveness plus readiness checks for database access, migration heads, and all mapped tables/columns | `src/health.py` |
| Containers and CI | Non-root API image; PostgreSQL/migration/API Compose services; PostgreSQL tests and a separate Compose smoke job | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` |

The current lifecycle is `PENDING -> RUNNING -> SUCCEEDED/FAILED`. Workers execute outside the API. A supported type is a worker-declared capability, and job permission policies determine which jobs it can claim. See [API details](api.md).

## Current limitations

- **No leases, heartbeats, or crash recovery.** A job stays running if the worker crashes or loses the claim response. The lease-related configuration fields and the `LOST` attempt enum do not implement expiry processing.
- **No retries or scheduling.** A reported failure is terminal. Claiming currently creates attempt number 1; there is no supported requeue operation.
- **No submission idempotency.** Repeating a successful submission creates another job. Lost responses cannot be safely retried by submission key.
- **No acknowledgement replay.** Repeating an accepted success/failure returns 400. Inspect the job after an uncertain outcome rather than assuming a repeat report will succeed.
- **Limited management/history APIs.** There are no update/delete or API-key rotation endpoints, and no endpoint for fetching attempt details. Job responses contain attempt IDs only. Worker identity represents a registered credential, not a separately fenced process instance.
- **Operational limits remain incomplete.** Payload size limits, rate limits, queue quotas, metrics, backup/restore procedures, and load targets are not implemented. Page sizes are bounded, but this is not a production-readiness claim.
- **Error mapping is selective.** PostgreSQL data errors return 422, and readiness failures return 503. Other application/storage failures may still return 500; readiness does not verify indexes or constraints.

Atomic claim exclusivity and worker ownership are implemented and tested. They do not guarantee eventual execution, crash recovery, or exactly-once external effects. The [roadmap](roadmap.md) describes the remaining work without treating it as part of every change.

## Verification performed

- The current working tree passed **118 PostgreSQL integration cases**, including deliberate overlapping claims, claim rollback, permissions, owned outcomes, oversized IDs, unsupported JSON characters, batch loading of attempts, and missing mapped tables/columns. Ruff, test-file formatting, syntax compilation, and diff checks passed during the runtime-fix verification.
- [GitHub Actions run #34](https://github.com/IvanVenkov712/Orqbit/actions/runs/42526225299) passed on commit `12ae981` on 2026-11-08. Its test job passed 76 cases, Ruff, and syntax checks. Its container job passed image build, migrations, authenticated job creation/read, database outage/reconnection, and persistence across container recreation.
- That GitHub run predates the pending runtime fixes. It does not establish that the current working tree has passed remote CI. The Compose smoke check has not been rerun locally for those fixes because the local Docker daemon was unavailable at the earlier attempt.

Setup and repeatable commands are in [testing](testing.md). This documentation refresh does not add or change runtime behavior.
