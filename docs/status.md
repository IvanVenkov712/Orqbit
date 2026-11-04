# Implementation status

Update on **2026-11-04**: environment-based PostgreSQL settings, locked dependencies, Alembic migrations, canonical statuses, and job timestamps now exist. A PostgreSQL integration suite and GitHub Actions workflow have been added. All 20 integration tests passed locally against PostgreSQL 18.3, and locked installation, Ruff, and syntax checks passed. Docker and Compose now provide a Python 3.13 image, PostgreSQL 18 with a persistent volume and health check, a separate migration service, and an API gated on migration success. A no-cache image build and the Compose smoke check passed locally, including job persistence across container recreation; the smoke check is also configured in CI. The workflows have not yet been run on GitHub. See [test setup](development.md#postgresql-integration-tests) and [container verification](development.md#docker-and-compose). API readiness checks remain unfinished; concurrent claiming and worker ownership remain unsafe. The inventory and verification record below are the historical review and have not been fully refreshed.

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
