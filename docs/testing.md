# Testing

## PostgreSQL integration tests

Create a separate PostgreSQL database once, using psql or your database administration tool:

```sql
CREATE DATABASE orqbit_test;
```

From the repository root in PowerShell, supply its connection URL with your local credentials:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:password@localhost:5432/orqbit_test"
uv sync --locked
uv run --locked pytest -q
```

For a POSIX shell, use `export TEST_DATABASE_URL='postgresql+psycopg://postgres:password@localhost:5432/orqbit_test'` before the same uv commands. The credentials above are local examples, not production defaults.

Tests require an explicit `TEST_DATABASE_URL` using the psycopg driver and a database name ending in `_test`; they do not fall back to your application database. The database user must be able to create schemas. Every run creates a uniquely named temporary schema, configures both the API and Alembic to use it, applies migrations from scratch, and drops only that schema on completion. Test connections use UTC. Jobs in other schemas are untouched. Each test clears jobs in the temporary schema, and requests use real commits and separate sessions. No SQLite substitute or `create_all()` is used. A missing or unavailable test database fails the suite instead of silently skipping it.

### What is tested and why

The pytest suite contains 28 cases, including parameterized variations. Its sources are [job tests](../tests/test_jobs.py), [health tests](../tests/test_health.py), and [migration tests](../tests/test_migrations.py). The [Compose smoke check](../tests/compose_smoke.py) runs separately.

| Area | What is checked | Why |
| --- | --- | --- |
| Create and read jobs | Creation returns an ID, `PENDING`, and empty result/error fields. A later HTTP request and a separate database session retrieve the saved job. | Confirm that accepted jobs are committed and available after the original request ends. |
| JSON persistence | Nested objects, arrays, Unicode, booleans, numbers, and null survive database storage and response serialization. Results and errors also round-trip. | Catch input/output corruption between JSON, PostgreSQL JSONB, and the API. |
| Invalid or absent resources | Missing required fields and wrong input types return 422 without inserting a job. Missing jobs and an empty claim queue return the current contract's 404 responses. | Reject malformed submissions and give callers predictable responses. |
| Claim eligibility | Only a compatible pending job is selected, returned as `RUNNING`, and saved in that state. | Avoid assigning unsupported work or selecting an already running job. This test does not cover concurrent workers. |
| Outcomes and transitions | Running jobs can succeed or fail and persist their result/error. Pending and terminal jobs reject either outcome with 400, leaving their stored state unchanged. | Record worker outcomes and prevent invalid updates from changing job state. |
| Timestamps | Creation/update timestamps are UTC-aware. Claiming and reporting an outcome advance `updated_at` while preserving `created_at`. | Keep job chronology meaningful. Tests seed an old timestamp instead of sleeping, and inspect PostgreSQL because timestamps are not exposed in job responses. |
| Migrations | Alembic prepares a fresh schema with the expected revision, JSONB columns, four canonical enum values, and required timezone-aware timestamps. A repeated upgrade preserves the table identity and saved job. | Check both first-time setup and safe reruns without relying on ORM table creation. |
| Liveness and readiness | Healthy PostgreSQL produces ready=200. A refused connection, absent migration records, outdated revision, missing table/column, or blocked schema query produces ready=503 with a generic, non-cacheable response. Liveness and its alias stay at 200; readiness returns to 200 after repair. | Distinguish a responding API from one with usable storage, and keep database details out of failure responses. |
| Containers and persistence | Compose builds and starts the stack; the runtime is non-root and excludes `.env` files and selected development tools. A job survives repeated migrations, a real database outage, and container recreation with the volume retained. | Catch packaging/startup problems and verify that container lifecycle changes preserve stored jobs. Database outage recovery here means reconnecting to PostgreSQL, not recovering abandoned running jobs. |

Real PostgreSQL checks JSONB, enums, transactions, and schema behavior that SQLite cannot faithfully verify. Temporary schemas and per-test cleanup prevent one case's data from affecting another; real commits and separate sessions ensure assertions do not rely only on objects cached in memory.

Run the other CI checks locally with:

```powershell
uv run --locked ruff check .
uv run --locked python -m compileall -q src migrations tests
```

GitHub Actions runs on pushes and pull requests with Python 3.13 and a healthy PostgreSQL 18 service. It installs locked dependencies, runs these checks, and runs pytest, whose fixture applies Alembic migrations. A separate job builds and exercises the Compose stack, including readiness during a database outage and persistence across container recreation. CI database credentials exist only for temporary services. These tests do not establish concurrent claim safety, ownership, or abandoned-job recovery.

## Docker Compose smoke check

An automated smoke check runs the complete flow in its own randomly named project with generated test credentials and a temporary database volume. It builds the image, waits for readiness, checks that the runtime excludes secrets and development tools, creates/reads a job, reruns migrations, stops PostgreSQL to verify live=200/ready=503, starts PostgreSQL again to verify recovery, recreates the containers while retaining the volume, and reads the same job. It removes only its own containers and volume afterward:

```powershell
python tests/compose_smoke.py
# Choose another local port if 18000 is occupied:
python tests/compose_smoke.py --port 18001
```

The smoke script uses only Python's standard library and Docker Compose; a host virtual environment or `.env` file is not required. It runs as a separate GitHub Actions job.

## Validation strategy

Use pure unit tests for retry calculation, request fingerprints, and error classification. Use real PostgreSQL integration tests for constraints, transactions, idempotency races, claim contention, ownership, and recovery. SQLite tests alone cannot validate PostgreSQL locking behavior.

Add HTTP tests for status codes, serialization, authentication, visibility, pagination, key conflicts, and acknowledgement replay. For resilience tests, kill a worker after claim and after an external effect, lose acknowledgement responses, race heartbeats with expiry, run multiple recovery instances, and restart services while work is active.

For an MVP acceptance demonstration: submit with an idempotency key; repeat it and get the same job; claim with one of two concurrent workers; renew its lease; kill the worker; observe an expired attempt and delayed retry; finish with a second worker; inspect both attempts and creator attribution; verify that the first worker's late completion is rejected. Repeat across a service restart.

The original documentation review used isolated in-memory probes. On 2026-11-04, all 28 integration tests passed against local PostgreSQL 18.3 (`pytest -q -p no:cacheprovider`, with the test URL supplied). Ruff, formatting of the added files, syntax compilation, and diff checks passed. `python tests/compose_smoke.py` passed, including real database outage/recovery and persistence across container recreation. The [manual demonstration](quickstart.md) passed separately in a fresh local clone with the proposed changes applied: no virtual environment or local configuration was copied, a new `.env.compose` was configured, the image was built with `--no-cache`, and the explicit migration/start/create/read/down/start/read/stop commands succeeded. The GitHub Actions workflows have not been executed on GitHub in this session. See the [verification record](status.md#verification-performed) for the original review scope.

When implementing features, update the current API and status docs together, mark roadmap milestones complete only after their acceptance checks pass, and record meaningful remaining limitations.
