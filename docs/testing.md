# Testing

## PostgreSQL integration tests

Create a separate PostgreSQL database once, using psql or your database administration tool:

```sql
CREATE DATABASE orqbit_test;
```

From the repository root in PowerShell, create your local test configuration:

```powershell
cd backend
Copy-Item .env.test.example .env.test
```

Edit `TEST_DATABASE_URL` in `.env.test` with your local PostgreSQL credentials, then run:

```powershell
uv sync --locked
uv run --locked pytest -q
```

Run the Python test and lint commands in this guide from `backend/`. The test setup reads `backend/.env.test`, regardless of the working directory. This file is ignored by Git; the example contains placeholder credentials. An existing `TEST_DATABASE_URL` environment variable takes precedence, so CI and terminal overrides continue to work. Alternatively, set `$env:TEST_DATABASE_URL` in PowerShell or `export TEST_DATABASE_URL='postgresql+psycopg://postgres:password@localhost:5432/orqbit_test'` in a POSIX shell. Tests do not read the application's `.env` for their database URL.

Tests require an explicit `TEST_DATABASE_URL` using the psycopg driver and a database name ending in `_test`; they do not fall back to your application database. Before collecting tests, `pytest_configure` selects a unique temporary schema and supplies the API/Alembic database URL and test-only settings, so importing models or the application during collection cannot capture the application's `.env` database URL. Configuration imported before this setup, or settings/engines that differ from the isolated URL before database setup, stop the run before migrations. The database user must be able to create schemas. Integration tests create the selected schema, apply migrations from scratch, and drop only that schema on completion; collection alone does not connect to PostgreSQL. Test connections use UTC. Data in other schemas is untouched. Each test clears application tables in foreign-key order within the temporary schema; migration records are retained. Requests use real commits and separate sessions. Fixtures supply authenticated user headers and workers with hashed API keys, without requiring a local `.env` file. No SQLite substitute or `create_all()` is used. A missing or unavailable test database fails the suite instead of silently skipping it.

### Adding focused coverage

Add or update tests for each requested behavior using the existing fixtures. Verify observable API responses and persisted state through separate sessions. Exercise PostgreSQL-specific locking with overlapping transactions, events, and bounded waits; use controlled timestamps instead of sleeps. Keep worker and producer tests in their own application directories.

Real PostgreSQL checks JSONB, enums, transactions, and schema behavior that SQLite cannot faithfully verify. Temporary schemas and per-test cleanup prevent one case's data from affecting another; real commits and separate sessions ensure assertions do not rely only on objects cached in memory.

Run the other CI checks locally from `backend/` with:

```powershell
uv run --locked ruff check .
uv run --locked python -m compileall -q src migrations tests
```

Repeat the configured checks for each change. CI uses a separate PostgreSQL test service and a separate Compose smoke job; use the same locked dependencies and test setup locally.

Existing backend coverage includes submission and permissions, concurrent claims, outcome replay, leases/recovery/retries, worker management, producer authentication and scoped jobs, key reissue/deactivation, the producer migration round trip, and rollback after database statement/lock timeouts. Producer tests include both mocked-session API cases and PostgreSQL-backed persistence/concurrency cases; mocked cases alone do not verify database guarantees.

## Independent applications and frontend

Run each runnable worker's and producer's checks from its own directory, using its own virtual environment:

```powershell
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

These application tests mock HTTP and, where needed, clocks; they do not need a running API or PostgreSQL. The `worker_foundation` directory is an incomplete template, not another runnable/tested worker. Refer to each application's README for its input and lifecycle cases.

From `frontend/`, use `npm ci`, `npm test`, `npm run lint`, and `npm run build` for the existing Vitest/Testing Library, Oxlint, and TypeScript/Vite checks. Browser tests mock API responses; they do not establish backend authorization or concurrency guarantees. The current GitHub Actions workflow runs backend checks and the Compose smoke job, not frontend or independent-application checks.

## Docker Compose smoke check

An automated backend smoke check runs in its own randomly named project with generated test credentials, a generated JWT signing key, and a temporary database volume. It builds the image, waits for readiness, checks that the runtime excludes secrets and development tools, registers and logs in a user, creates/reads a private job using its bearer token, reruns migrations, stops PostgreSQL to verify live=200/ready=503, starts PostgreSQL again to verify reconnection, verifies abandoned-attempt recovery and late-report rejection, recreates the containers while retaining the volume, and reads the same job. It removes only its own containers and volume afterward. It does not run the browser or an independent worker/producer application. Run it from the repository root (`cd ..` if you are in `backend/`):

```powershell
python backend/tests/compose_smoke.py
# Choose another local port if 18000 is occupied:
python backend/tests/compose_smoke.py --port 18001
```

The smoke script uses only Python's standard library and Docker Compose; a host virtual environment or `.env` file is not required. Run it with `MAX_ATTEMPTS` unset or set to 1, since its abandoned-attempt scenario expects terminal failure after the first execution. Bounded retry cycles are covered by pytest separately. The script runs as a separate GitHub Actions job.

## Validation strategy

- Add focused tests when introducing transient-error classification, jitter, hard deadlines, process-instance fencing, or manual replay.
- Kill live workers after claim and after external effects; lose claim/outcome responses and interrupt network access.
- Restart API, PostgreSQL, recovery, and worker processes while work is active; verify persisted schedules, retry budgets, and late-report rejection.
- Exercise multiple live recovery processes under backlog and measure expiry lag.
- Demonstrate idempotent external actions and a complete browser/API/independent-worker retry flow.
- Add representative load, resource-limit, and backup/restore checks when their acceptance targets are defined.

Use the [backend roadmap](roadmap.md), [frontend roadmap](../frontend/docs/roadmap.md), and [outstanding acceptance requirements](requirements.md) to select further work.
