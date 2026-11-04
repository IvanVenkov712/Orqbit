# Development and verification

## Repository layout

```text
src/
  main.py                  FastAPI application; no schema creation at import
  config.py                Validated environment settings
  database.py              PostgreSQL engine and session dependency
  models.py                Job model and status enum
  api/
    routers/job_router.py  Create, list, and read jobs
    routers/claim_router.py Claim, success, and failure operations
    dto/jobs.py            Job request/response models
    dto/claims.py          Worker request models
Dockerfile                 Empty placeholder
pyproject.toml             Dependencies, dev tools, pytest and Ruff configuration
uv.lock                    Exact dependency versions
migrations/                Alembic environment and versioned schema changes
tests/                     PostgreSQL-backed HTTP and migration tests
.github/workflows/ci.yml    Checks on pushes and pull requests
docs/                      Current status and proposed implementation design
```

## Running the existing prototype

Use Python 3.13 and `uv sync --locked` to install the declared dependencies. Copy `.env.example` to `.env` and set your local PostgreSQL credentials. Create the database before running `uv run --locked alembic upgrade head`. The settings also require positive `LEASE_SECONDS` and `PROTRACTION_SECONDS` values, shown in the example file; lease and heartbeat behavior itself is not implemented.

In an environment containing those dependencies, run from the repository root:

```sh
python -m uvicorn main:app --app-dir src --reload
```

If using an existing Windows virtual environment, the equivalent interpreter invocation is:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir src --reload
```

`--app-dir src` is necessary for the current top-level imports. The reload flag is for local development. Run from the repository root so settings find `.env`. PostgreSQL stores database state; importing `main` does not create or alter tables.

The API normally exposes interactive docs at `http://127.0.0.1:8000/docs` and its schema at `/openapi.json`. Current routes are prototypes; see [status](status.md) for verification limits.

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

The suite covers nested JSON/Unicode persistence, creation and retrieval, invalid submissions, missing jobs, claim eligibility, an empty queue, success/failure, invalid transitions, canonical PostgreSQL enum values, timezone-aware timestamps, and repeated migration upgrades that preserve rows. Timestamp update tests use an explicit old timestamp instead of sleeps. Timestamps are checked in PostgreSQL because the current response model does not expose them.

Run the other CI checks locally with:

```powershell
uv run --locked ruff check .
uv run --locked python -m compileall -q src migrations tests
```

GitHub Actions runs on pushes and pull requests with Python 3.13 and a healthy PostgreSQL 18 service. It installs locked dependencies, runs these checks, and runs pytest, whose fixture applies Alembic migrations. CI database credentials exist only for that temporary service. These tests do not establish concurrent claim safety, ownership, restart recovery, or readiness behavior.

## Target environment and Compose workflow

Environment-based PostgreSQL settings and Alembic migrations exist. Complete the remaining container and operational setup in roadmap milestone 1:

| Configuration | Intended use |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection URL supplied through environment/secret configuration |
| Authentication settings | Credential verification and client/worker role mapping; secret values stay outside source control |
| Lease/heartbeat/runtime settings | Default coordination timing with per-job-type runtime limits |
| Recovery settings | Scan interval and bounded batch size |
| Resource/retention settings | Body/page limits, queue quotas, history/key retention |

Provide an example environment file containing placeholders, lock dependencies, and choose a supported PostgreSQL version. Compose should have API and PostgreSQL services, an explicit migration command/service, and a separately runnable recovery service once implemented. Gate startup on health/migration completion and persist the database volume. Provide an optional example worker for end-to-end demonstrations. Publish exact build/start/migrate/stop commands when these artifacts work; `docker compose up` is not currently an available setup path.

## Validation strategy

Use pure unit tests for retry calculation, request fingerprints, and error classification. Use real PostgreSQL integration tests for constraints, transactions, idempotency races, claim contention, ownership, and recovery. SQLite tests alone cannot validate PostgreSQL locking behavior.

Add HTTP tests for status codes, serialization, authentication, visibility, pagination, key conflicts, and acknowledgement replay. For resilience tests, kill a worker after claim and after an external effect, lose acknowledgement responses, race heartbeats with expiry, run multiple recovery instances, and restart services while work is active.

For an MVP acceptance demonstration: submit with an idempotency key; repeat it and get the same job; claim with one of two concurrent workers; renew its lease; kill the worker; observe an expired attempt and delayed retry; finish with a second worker; inspect both attempts and creator attribution; verify that the first worker's late completion is rejected. Repeat across a service restart.

The original documentation review used isolated in-memory probes. On 2026-11-04, the committed integration suite passed all 20 tests against local PostgreSQL 18.3. Locked dependency installation, Ruff, and syntax checks also passed. The GitHub Actions workflow has been added but has not been executed on GitHub in this session. See the [verification record](status.md#verification-performed) for the original review scope.

When implementing features, update the current API and status docs together, mark roadmap milestones complete only after their acceptance checks pass, and record meaningful remaining limitations.
