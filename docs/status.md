# Implementation status

Update on **2026-11-04**: the PostgreSQL foundation now includes validated environment settings, locked dependencies, Alembic migrations, canonical statuses, UTC timestamps, a Docker image, and Compose services for PostgreSQL, migration, and the API. `/health/live` reports process liveness (`/health` remains an alias). `/health/ready` checks database access, migration heads, and required job columns, returning 503 on failure. Compose uses this readiness endpoint as the API health check.

All **28 PostgreSQL integration tests passed locally**, including database/schema failure cases and recovery. Ruff, formatting checks for the new files, syntax compilation, and diff checks passed. The Docker smoke check verified a real database outage (live=200, ready=503), reconnection, repeated migrations, and job persistence after container recreation. The [clean-checkout demonstration](quickstart.md) also passed in a fresh local clone with the proposed changes applied, without copied environment files or a virtual environment; it used a no-cache build, explicit migration, and the documented PowerShell create/read/recreate/read commands. The demonstration containers were stopped while retaining their database volume.

Both test groups are configured in GitHub Actions; remote workflow execution is still pending. See [test setup](development.md#postgresql-integration-tests) and [container verification](development.md#docker-and-compose). Concurrent claiming and worker ownership remain unsafe. The inventory and verification record below are the historical review and have not been fully refreshed.

Reviewed on **2026-11-03** against the working tree at commit `db293e4`. This is a code-based snapshot, not a production-readiness assessment. Update it when behavior changes.

## Feature inventory

“Prototype” means a code path exists; it does not imply concurrency safety or production validation.

| Requirement | Status | Evidence / limitation |
| --- | --- | --- |
| Submit jobs | Prototype | `src/api/routers/job_router.py`: inserts type and JSON parameters with pending status |
| Read/list jobs | Prototype | Same router; lookup returns 404 when absent; list is unbounded |
| Pull jobs by type | Prototype, unsafe concurrently | `src/api/routers/claim_router.py`: selects a matching pending job, then updates it without a lock or conditional claim |
| Report success/failure | Prototype | Same router; accepts updates to running jobs without identifying their worker |
| Persist job state | Prototype | `src/database.py`: hard-coded `sqlite:///orqbit.db` |
| PostgreSQL connection | Missing | PostgreSQL JSONB types appear in the model, but no PostgreSQL URL, driver declaration, provisioning, or migration exists |
| Worker heartbeat / lease | Missing | No worker model, heartbeat endpoint, lease, or expiry processing |
| Retry failed/abandoned jobs | Missing | Failure sets `FAILED`; no scheduler, retry policy, or recovery process |
| Reliable creator identity | Missing | No authentication dependency or creator field |
| Reliable worker identity | Missing | No worker identity, assignment, attempt ID, or claim token |
| Docker Compose | Missing | `Dockerfile` is empty; no Compose file exists |
| Submission idempotency | Missing | Each accepted POST inserts a new job; no key or uniqueness constraint |
| Execution idempotency support | Missing | No attempt-scoped acknowledgement or documented worker protocol in code |
| Attempt history | Missing | One mutable job row stores the current result/error; no attempt table |
| Dependency declaration | Missing | `pyproject.toml` is empty; no lock file |
| Tests / CI | Missing | No committed test suite or CI workflow found |
| Migrations / operational health | Missing | Tables are created at import; no migrations, explicit readiness/liveness endpoints, or recovery service |

## Current problems, in priority order

| Priority | Problem | Consequence | Recommended resolution |
| --- | --- | --- | --- |
| P0 | Claims use separate select/update operations without concurrency control | Two workers can receive the same job | Atomic PostgreSQL claim transaction; create attempt and lease in that transaction |
| P0 | No authentication or authorization | Anyone with API access can submit, read, claim, or finish jobs | Authenticate client/worker principals; enforce creator access and worker capabilities |
| P0 | Completion/failure only checks `RUNNING`, without ownership or a conditional update | An unrelated worker can update a job; competing terminal updates can race | Require current worker instance, attempt ID, and lease token; update conditionally in one transaction |
| P0 | No lease expiry or recovery | A worker crash leaves its job running indefinitely | Per-attempt heartbeats, expiry, maximum runtime, and a durable recovery loop |
| P1 | PostgreSQL is not actually configured | Intended durability and concurrency design cannot be validated | Environment-based settings, PostgreSQL driver, migrations, integration tests |
| P1 | No submission idempotency | A client retry after a lost response creates another job | Creator-scoped unique key and request fingerprint, committed with the job |
| P1 | No retries or attempt history | Transient failures require manual intervention; prior executions cannot be reconstructed | Attempt records first, then bounded retries with backoff |
| P1 | Empty packaging/container files | A clean checkout has no declared install/build procedure | Declare supported Python/dependencies, lock them, implement Docker/Compose |
| P1 | `Base.metadata.create_all(engine)` runs while importing `src/main.py` | Startup depends on DB access and DDL permissions; existing tables are not migrated | Versioned migrations run separately; application readiness checks |
| P2 | `JobStatus` contains both `PENDING` and `pending` | Ambiguous status vocabulary; lowercase pending rows would not match the uppercase claim filter | Canonical enum values and a migration for existing data |
| P2 | No bounds on list size, request bodies, or supported-type lists | Expensive queries, oversized data, and avoidable resource pressure | Pagination, validation, body limits, rate limits, and indexes |
| P2 | Job schema has no timestamps | Queue age, runtime, and failure chronology cannot be measured reliably | UTC creation/update timestamps and attempt lifecycle timestamps |

P0 items block reliable multi-worker use. P1 items block a useful durable MVP. P2 items still need resolution before exposing the service to uncontrolled traffic.

## Database and serialization observations

`src/models.py` uses the PostgreSQL dialect's `JSONB` type while `src/database.py` selects SQLite. An isolated in-memory SQLite schema check **passed in the installed local environment**. Do not treat this mismatch as a reproduced startup failure, or as proof of portability across undeclared dependency versions. PostgreSQL behavior is untested. The intended solution is to use PostgreSQL consistently, rather than depend on SQLite compatibility with dialect-specific types. See the [SQLAlchemy JSONB documentation](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.JSONB).

`JobRead` has no explicit Pydantic attribute-reading configuration. Direct `JobRead.model_validate(job)` failed in the checked environment, but FastAPI's response-field conversion accepted the same ORM object. This is not a confirmed HTTP response bug. Make the intended conversion explicit and cover it through HTTP tests when establishing the supported dependency versions. See [Pydantic's ORM validation guidance](https://github.com/pydantic/pydantic/blob/main/docs/migration.md).

## Verification performed

- Read all tracked application files and repository configuration.
- Compiled all Python source files for syntax without writing bytecode.
- Created the model schema in in-memory SQLite.
- Exercised create, get, list, claim, succeed, and fail by directly calling the existing handlers with an in-memory SQLAlchemy session. Both final outcomes were asserted.
- Checked conversion of an ORM job through FastAPI's response-field adapter.

Local probes used Python 3.13.7, FastAPI 0.162.0, SQLAlchemy 2.1.6, and Pydantic 2.14.2. These are observed local versions, not declared project requirements.

No HTTP end-to-end test, PostgreSQL test, concurrent-worker test, Docker build, or clean-install test was completed. A file-backed startup probe in an OS temporary directory was blocked by filesystem permissions; it provides no evidence of an application defect. The in-memory handler checks do not establish production reliability. No application behavior was changed during this documentation pass.
