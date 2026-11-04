# Development and verification

## Repository layout

```text
src/
  main.py                  FastAPI application; no schema creation at import
  config.py                Validated environment settings
  database.py              PostgreSQL engine and session dependency
  health.py                Read-only database/schema readiness checks
  models.py                Job model and status enum
  api/
    routers/job_router.py  Create, list, and read jobs
    routers/claim_router.py Claim, success, and failure operations
    dto/jobs.py            Job request/response models
    dto/claims.py          Worker request models
Dockerfile                 Python 3.13 API/migration image with locked runtime dependencies
docker-compose.yml         PostgreSQL, migration, and API services
.dockerignore              Allowlist of files needed to build the image
.env.compose.example       Local container configuration template
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

The suite covers nested JSON/Unicode persistence, creation and retrieval, invalid submissions, missing jobs, claim eligibility, an empty queue, success/failure, invalid transitions, canonical PostgreSQL enum values, timezone-aware timestamps, and repeated migration upgrades that preserve rows. Health tests cover healthy PostgreSQL, a refused connection, missing migration records, outdated revisions, missing tables/columns, and a schema query blocked by a table lock. They also verify that liveness remains available and readiness recovers when the problem is removed. Timestamp update tests use an explicit old timestamp instead of sleeps. Timestamps are checked in PostgreSQL because the current response model does not expose them.

Run the other CI checks locally with:

```powershell
uv run --locked ruff check .
uv run --locked python -m compileall -q src migrations tests
```

GitHub Actions runs on pushes and pull requests with Python 3.13 and a healthy PostgreSQL 18 service. It installs locked dependencies, runs these checks, and runs pytest, whose fixture applies Alembic migrations. A separate job builds and exercises the Compose stack, including readiness during a database outage and persistence across container recreation. CI database credentials exist only for temporary services. These tests do not establish concurrent claim safety, ownership, or abandoned-job recovery.

## Docker and Compose

The image uses Python 3.13, matching the CI version and the project's declared Python requirement. A build stage uses uv 0.13.7 to install dependencies with `uv sync --locked --no-dev --no-install-project --no-cache`. The final stage contains the virtual environment, application, and migrations; it runs as a non-root user. It does not include uv, tests, or development dependencies. `.dockerignore` includes only the application, migration, and dependency files needed for the build, excluding local environments, credentials, Git, caches, and documentation.

Create `.env.compose` from `.env.compose.example`, choosing matching values for `POSTGRES_PASSWORD` and the password in `DATABASE_URL`. URL-encode reserved password characters in the URL. The hostname is `db` inside Compose and usually `localhost` when running Python directly on your host. The real environment files are ignored by Git and excluded from the image. Compose requires explicit database credentials; it does not supply production password defaults. Existing shell environment variables take precedence over values in `--env-file`, so unset any host `DATABASE_URL` when switching to Compose or set it to the container URL.

The services are:

| Service | Behavior |
| --- | --- |
| `db` | PostgreSQL 18 with UTC sessions, a `pg_isready` health check, and a named `postgres_data` volume mounted at `/var/lib/postgresql`, the volume location used by PostgreSQL 18 images |
| `migrate` | Uses the API image, waits for a healthy database, runs `alembic upgrade head`, and exits |
| `api` | Uses the same image, waits for a healthy database and successful migrations, and runs Uvicorn on port 8000 without reload |

The host API port defaults to `127.0.0.1:8000`; set `API_PORT` to change it. The database port is not published to the host. Startup gating uses Compose's `service_healthy` and `service_completed_successfully` conditions ([Docker documentation](https://docs.docker.com/compose/how-tos/startup-order/)). The shared image receives application configuration at runtime through environment variables.

From the repository root:

```powershell
Copy-Item .env.compose.example .env.compose
# Edit .env.compose before starting.
docker compose --env-file .env.compose config --quiet
docker compose --env-file .env.compose up --build --wait --wait-timeout 120 api
docker compose --env-file .env.compose ps --all
docker compose --env-file .env.compose logs migrate api
```

The startup command automatically runs the separate migration service and waits for the API's `/health/ready` health check. The [clean-checkout guide](quickstart.md) gives the complete manual build/migrate/start and persistence demonstration. To run migration operations explicitly using the built image:

```powershell
docker compose --env-file .env.compose run --rm migrate
docker compose --env-file .env.compose run --rm migrate alembic current
```

Use `up --build --wait --wait-timeout 120 api` after code or migration changes. `restart` does not rebuild the image or apply new migrations. Normal `down` retains the database volume. `down --volumes` deletes it and all stored jobs. Credentials in `.env.compose` initialize a new database volume; changing them later does not change credentials inside an existing database.

An automated smoke check runs the complete flow in its own randomly named project with generated test credentials and a temporary database volume. It builds the image, waits for readiness, checks that the runtime excludes secrets and development tools, creates/reads a job, reruns migrations, stops PostgreSQL to verify live=200/ready=503, starts PostgreSQL again to verify recovery, recreates the containers while retaining the volume, and reads the same job. It removes only its own containers and volume afterward:

```powershell
python tests/compose_smoke.py
# Choose another local port if 18000 is occupied:
python tests/compose_smoke.py --port 18001
```

The smoke script uses only Python's standard library and Docker Compose; a host virtual environment or `.env` file is not required. It runs as a separate GitHub Actions job. There is no recovery executable or service yet. The PostgreSQL health check and migration dependency control initial startup; the API health check continues checking database/schema readiness after startup. An unhealthy container is reported as such; Docker Compose does not automatically restart it solely because a health check fails.

## Validation strategy

Use pure unit tests for retry calculation, request fingerprints, and error classification. Use real PostgreSQL integration tests for constraints, transactions, idempotency races, claim contention, ownership, and recovery. SQLite tests alone cannot validate PostgreSQL locking behavior.

Add HTTP tests for status codes, serialization, authentication, visibility, pagination, key conflicts, and acknowledgement replay. For resilience tests, kill a worker after claim and after an external effect, lose acknowledgement responses, race heartbeats with expiry, run multiple recovery instances, and restart services while work is active.

For an MVP acceptance demonstration: submit with an idempotency key; repeat it and get the same job; claim with one of two concurrent workers; renew its lease; kill the worker; observe an expired attempt and delayed retry; finish with a second worker; inspect both attempts and creator attribution; verify that the first worker's late completion is rejected. Repeat across a service restart.

The original documentation review used isolated in-memory probes. On 2026-11-04, all 28 integration tests passed against local PostgreSQL 18.3 (`pytest -q -p no:cacheprovider`, with the test URL supplied). Ruff, formatting of the added files, syntax compilation, and diff checks passed. `python tests/compose_smoke.py` passed, including real database outage/recovery and persistence across container recreation. The [manual demonstration](quickstart.md) passed separately in a fresh local clone with the proposed changes applied: no virtual environment or local configuration was copied, a new `.env.compose` was configured, the image was built with `--no-cache`, and the explicit migration/start/create/read/down/start/read/stop commands succeeded. The GitHub Actions workflows have not been executed on GitHub in this session. See the [verification record](status.md#verification-performed) for the original review scope.

When implementing features, update the current API and status docs together, mark roadmap milestones complete only after their acceptance checks pass, and record meaningful remaining limitations.
