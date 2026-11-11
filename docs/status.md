# Implementation status

Reviewed on **2026-11-11** against the current code and tests. Verification of a specific GitHub commit is recorded separately below.

## Feature inventory

| Area | Current behavior | Evidence |
| --- | --- | --- |
| User identity | Registration, Argon2 password hashing, JWT login, and active-user checks | `backend/src/api/routers/auth_router.py`, `backend/src/services/user_auth.py` |
| Worker identity | User-owned workers; generated API keys stored as SHA-256 hashes; active-worker checks | `backend/src/api/routers/worker_router.py`, `backend/src/services/worker_auth.py` |
| Job submission | Authenticated creator, nonblank type, JSON-object parameters, explicit permission policy, pending status; required creator-scoped `Idempotency-Key` with matching replay and 409 on changed content | `backend/src/api/routers/job_router.py`, `backend/src/services/job.py`, `backend/src/dto/job.py` |
| Reads and lists | Permission-aware job/worker lookup; filtered lists ordered by descending ID with limit/offset pagination | Job and worker routers |
| Claims | Oldest accessible compatible pending job by ID; PostgreSQL `FOR UPDATE SKIP LOCKED`; initial lease uses database time; job update and attempt insert commit together | `backend/src/services/job_execution.py` |
| Attempt heartbeats | Authenticated `POST /workers/{attempt_id}/heartbeat`; row-locked ownership/status/expiry checks using database time; renewal cannot shorten a lease | `backend/src/api/routers/claim_router.py`, `backend/src/services/job_execution.py` |
| Outcomes | Owning worker reports by attempt ID; first outcome requires a running attempt and unexpired lease; job and attempt update together; exact accepted replays return 200 even after the deadline, expired new reports return 400, conflicting/lost-attempt reports return 409 | `backend/src/services/job_execution.py` |
| Attempts | Worker attribution, parameters, status, result/error, lease deadline, and UTC creation/update timestamps; authorized `GET /jobs/{job_id}/attempts` returns details ordered by descending attempt number with limit/offset pagination | `backend/src/api/routers/job_router.py`, `backend/src/dto/job_attempt.py` |
| Persistence | PostgreSQL with JSONB, synchronous SQLAlchemy sessions, Alembic migrations, and constraints allowing at most one running attempt per job | Models, `backend/src/database.py`, `backend/migrations/` |
| Input errors | Pydantic validation and generic 422 responses for PostgreSQL data errors, including oversized IDs and null characters | DTOs, `backend/src/main.py` |
| Health | Liveness plus readiness checks for database access, migration heads, and all mapped tables/columns | `backend/src/health.py` |
| Containers and CI | Non-root API image; PostgreSQL/migration/API Compose services; PostgreSQL tests and a separate Compose smoke job | `backend/Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` |
| Example worker | Independently installable `add_numbers` worker with its own configuration, dependencies, and tests; claims and reports through HTTP only | `examples/workers/add_numbers/`, [worker guide](../examples/workers/add_numbers/README.md) |

The current lifecycle is `PENDING -> RUNNING -> SUCCEEDED/FAILED`. Workers execute outside the API. A supported type is a worker-declared capability, and job permission policies determine which jobs it can claim. See [API details](api.md).

## Current limitations

- **No automatic lease recovery.** Expiry blocks new heartbeats and outcomes but leaves both job and attempt stored as `RUNNING`. A worker crash or lost claim response can leave a job stuck indefinitely; no process marks the attempt `LOST` or requeues it.
- **Attempt heartbeats only.** There is no separate worker-process heartbeat or hard execution deadline. A worker can keep renewing a stuck handler indefinitely. The example worker does not send heartbeats and must report within its initial lease.
- **No retries or scheduling.** A reported failure is terminal. Claiming currently creates attempt number 1; there is no supported requeue operation.
- **Idempotency retention follows job storage.** Keys remain reserved while the job exists; there is no separate expiry or tombstone policy. Migrated legacy jobs cannot replay their original submissions. Submission deduplication and outcome replay do not deduplicate external worker side effects.
- **Limited management APIs.** There are no update/delete or API-key rotation endpoints. Worker identity represents a registered credential, not a separately fenced process instance.
- **Operational limits remain incomplete.** Payload size limits, rate limits, queue quotas, metrics, backup/restore procedures, and load targets are not implemented. Page sizes are bounded, but this is not a production-readiness claim.
- **Error mapping is selective.** PostgreSQL data errors return 422, and readiness failures return 503. Other application/storage failures may still return 500; readiness does not verify indexes or constraints.

Atomic claim exclusivity and worker ownership are implemented and tested. They do not guarantee eventual execution, crash recovery, or exactly-once external effects. The [roadmap](roadmap.md) describes the remaining work without treating it as part of every change.

## Verification performed

- On **2026-11-11**, the backend passed **256 tests** with real PostgreSQL, using `.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --tb=short` from `backend/`. The run used the isolated test database/schema and ran outside the sandbox to allow pytest's temporary-directory access. Coverage includes initial leases with a skewed model clock, renewal without shortening, owner/status checks, expired heartbeat/outcome rejection, accepted outcome replays after expiry, heartbeat/outcome contention, and expiry rechecked after an actual PostgreSQL lock wait. Lease migration tests cover historical terminal attempts and transactional refusal of legacy running attempts. Ruff (`ruff check .`), formatting of the changed job tests, syntax compilation (`python -m compileall -q src migrations tests`), and `git diff --check` passed.
- On the same date, Compose configuration and application settings were validated for both the example renewal window and an environment override. This did not execute the container smoke check; the Docker daemon was unavailable.
- On **2026-11-10**, the then-current backend passed **165 tests**, using real PostgreSQL for integration coverage. This includes submission-key validation, matching/conflicting/concurrent submissions, exact outcome replay, attempt-history permissions and pagination, overlapping claims, rollback, migrations, and readiness. From `backend/`, `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp-docs-verified` passed outside the sandbox after the initial run hit a Windows temporary-directory permission error. Ruff (`python -m ruff check src migrations tests`), syntax compilation (`python -m compileall -q src migrations tests`), and `git diff --check` also passed.
- [GitHub Actions run #34](https://github.com/IvanVenkov712/Orqbit/actions/runs/42526225299) passed on commit `12ae981` on 2026-11-08. Its test job passed 76 cases, Ruff, and syntax checks. Its container job passed image build, migrations, authenticated job creation/read, database outage/reconnection, and persistence across container recreation.
- That GitHub run predates the current implementation. It does not establish that the current working tree has passed remote CI. The Compose smoke check and manual Docker quickstart were not rerun during this documentation update.

Setup and repeatable commands are in [testing](testing.md). This documentation refresh does not add or change runtime behavior.
