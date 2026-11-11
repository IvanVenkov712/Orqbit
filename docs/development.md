# Development and verification

## Repository layout

```text
backend/
  src/
    main.py                FastAPI application; no schema creation at import
    config.py              Validated environment settings
    database.py            PostgreSQL engine and session dependency
    health.py              Read-only database/schema readiness checks
    models/                Jobs, users, workers, permissions, attempts, and timestamps
    dto/                   Pydantic requests and responses
    services/              Authentication, access rules, submission, and job lifecycle operations
    api/routers/           Auth, user, job, worker, claim/outcome, and health routes
  Dockerfile               Python 3.13 API/migration image with locked runtime dependencies
  .dockerignore            Allowlist of files needed to build the image
  .env.example             Local application configuration template
  .env.test.example        Local test database configuration template
  pyproject.toml           Dependencies, dev tools, pytest and Ruff configuration
  uv.lock                  Exact dependency versions
  alembic.ini              Alembic configuration
  migrations/              Alembic environment and versioned schema changes
  tests/                   PostgreSQL tests and the separate Compose smoke script
docker-compose.yml         PostgreSQL, migration, and API services
.env.compose.example       Local container configuration template
.github/workflows/ci.yml    Checks on pushes and pull requests
docs/                      Current status and proposed implementation design
```

## Running the API locally

This setup runs without Docker. Install Python 3.13, uv, and PostgreSQL 18 locally. Start the PostgreSQL service on port 5432 and have your database user's password ready.

Create the `orqbit` database once, using PostgreSQL's command-line tools on your PATH:

```powershell
psql -h localhost -p 5432 -U postgres -d postgres -c "CREATE DATABASE orqbit;"
```

Enter your PostgreSQL password when prompted. Substitute your own database user for `postgres` if needed. Alternatively, create the database in pgAdmin, owned by the user you will put in `DATABASE_URL`. Reuse an existing database by skipping creation; review the [migration considerations](#existing-databases) before upgrading existing data.

In a PowerShell terminal, starting from the repository root:

```powershell
cd backend
uv sync --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv run --locked python -c "import secrets; print(secrets.token_hex(32))"
```

Edit `backend/.env` before continuing:

- Set `DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/orqbit`, replacing the user and password with your local credentials. URL-encode reserved characters in the password.
- Replace `SECRET_KEY=replace_with_secret_key` with the generated 64-character lowercase hexadecimal value. Keep an existing valid key when reusing your configuration.
- Retain the other example settings: `LEASE_SECONDS=120`, `LEASE_EXTENSION_SECONDS=60`, `ALGORITHM=HS256`, and `ACCESS_TOKEN_EXPIRE_MINUTES=30`. The three timing settings must be positive. `LEASE_SECONDS` sets the initial attempt lease; `LEASE_EXTENSION_SECONDS` sets the window from the current database time on renewal. Rename the former `PROTRACTION_SECONDS` setting in existing environment files; no compatibility alias is provided.

The real environment files are ignored by Git.

Continue running Python commands from `backend/`; run Docker Compose commands from the repository root. Apply migrations and start the API:

```powershell
uv run --locked alembic upgrade head
uv run --locked uvicorn main:app --app-dir src --reload --port 8000
```

If using an existing Windows virtual environment, the equivalent interpreter invocation is:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir src --reload
```

`--app-dir src` is necessary for the current top-level imports. The reload flag is for local development. Run from `backend/` so settings find `backend/.env`. Configure your IDE to use `backend/.venv` as its interpreter environment and `backend/` as the API working directory. PostgreSQL stores database state; importing `main` does not create or alter tables.

The API normally exposes interactive docs at `http://127.0.0.1:8000/docs` and its schema at `/openapi.json`. Register/log in a user for job and worker-management routes. Workers claim and report with their own API keys and report by attempt ID. See [API](api.md) for examples and [status](status.md) for verification limits.

Keep the API terminal running. In a second PowerShell terminal, check database and schema readiness:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health/ready
```

Expect `status: ready`. If the check fails, inspect the API terminal, PostgreSQL service, database credentials, and migration output. To open the browser interface, continue with the [frontend setup without Docker](../frontend/docs/development.md#without-docker-powershell); it covers Node.js/npm, starting Vite, registration, and login. Stop each development server with `Ctrl+C` in its terminal. PostgreSQL retains accounts and jobs.

## Job coordination

Clients submit with a required creator-scoped `Idempotency-Key`; matching retries return the existing job, and changed content returns 409. Workers authenticate with `X-API-Key` and claim without a request body; their supported job types are registered on the server. A claim returns an execution attempt, and the worker reports its outcome by that attempt's ID. Clients can read job status, result/error, and attempt IDs, then fetch paginated attempt details from `GET /jobs/{job_id}/attempts`. The [example worker guide](../examples/workers/add_numbers/README.md) walks through this flow.

Claims use a PostgreSQL transaction with `FOR UPDATE SKIP LOCKED`; claiming creates an attempt with an initial lease and marks the job running in that transaction. Heartbeats and outcome reports lock the attempt and check worker ownership, running status, and lease expiry using PostgreSQL `clock_timestamp()` after locking. Heartbeat renewal cannot shorten the current deadline. An accepted outcome updates job and attempt together; an exact replay remains supported after the lease deadline. See the [API reference](api.md#attempt-heartbeats-and-leases) for the protocol and error responses. These operations coordinate work; the API does not execute worker handlers.

Lease recovery and retries remain planned. Expiry rejects new heartbeats and outcomes but does not change the stored `RUNNING` status or requeue a job. A crashed worker can leave a job running indefinitely. Separate worker-process liveness and hard execution deadlines are not implemented. There is no exactly-once execution guarantee. Future retries will require idempotent worker side effects; submission deduplication alone cannot prevent a worker from repeating an external action.

## Existing databases

Migrations run explicitly, never through `create_all()` at app import. Upgrade with `uv run --locked alembic upgrade head` from `backend/`, or use the Compose migration command below.

Migration `476550d0c277` adds users, workers, permissions, and attempts. It refuses to upgrade legacy `RUNNING` jobs because worker ownership cannot be reconstructed; resolve those jobs deliberately before upgrading. Other legacy jobs retain their values and become private jobs owned by an inactive `__legacy_jobs__` account. Reassign them explicitly before use; no ownership-transfer endpoint is implemented. These migration behaviors are covered by PostgreSQL integration tests.

Migration `4610066358ca` adds required submission keys and request fingerprints, unique per creator and key. Existing jobs receive synthetic `legacy-job:<job_id>` keys and a `legacy` fingerprint marker; they retain their data but cannot replay their original submissions. See the [API reference](api.md#jobs) for the current submission contract.

Migration `43dcc043466c` adds the required timezone-aware `job_attempts.lease_expires_at` column. It locks the attempts table and refuses to upgrade if any legacy attempt is `RUNNING`; stop new claims and resolve those attempts before upgrading. Existing `SUCCEEDED`, `FAILED`, and `LOST` attempts retain their data and receive `updated_at` as a synthetic deadline, since their real lease deadlines were never recorded. The column is added nullable, backfilled, and then made non-nullable without a database default. A rejected upgrade rolls back without changing the revision or schema. Downgrade removes the column and its lease values.

## PostgreSQL integration tests

See the [testing guide](testing.md) for database setup, commands, coverage, and CI checks.

## Docker and Compose

Run Docker Compose commands from the repository root (`cd ..` if you are in `backend/`). Compose uses `./backend` as the build context, so paths in `backend/Dockerfile` and `backend/.dockerignore` are relative to that directory. Keep `.env.compose` at the repository root.

The image uses Python 3.13, matching the CI version and the project's declared Python requirement. A build stage uses uv 0.13.7 to install dependencies with `uv sync --locked --no-dev --no-install-project --no-cache`. The final stage contains the virtual environment, application, and migrations; it runs as a non-root user. It does not include uv, tests, or development dependencies. `.dockerignore` includes only the application, migration, and dependency files needed for the build, excluding local environments, credentials, Git, caches, and documentation.

Create `.env.compose` from `.env.compose.example`, choosing matching values for `POSTGRES_PASSWORD` and the password in `DATABASE_URL`, and replacing the `SECRET_KEY` placeholder with a generated signing key. The [quickstart](quickstart.md#1-configure-the-stack) includes PowerShell key generation without host Python. URL-encode reserved password characters in the URL. The hostname is `db` inside Compose and usually `localhost` when running Python directly on your host. The real environment files are ignored by Git and excluded from the image. Compose requires explicit credentials and is invoked with `--env-file .env.compose`. Shell variables override that file. Keep the signing key stable across container recreation if existing unexpired tokens should remain valid.

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
# Configure database credentials and a generated SECRET_KEY before starting.
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

For the automated container check, see the [Compose smoke check](testing.md#docker-compose-smoke-check).

There is no recovery executable or service yet. The PostgreSQL health check and migration dependency control initial startup; the API health check continues checking database/schema readiness after startup. An unhealthy container is reported as such; Docker Compose does not automatically restart it solely because a health check fails.

## Validation strategy

See the [testing guide](testing.md#validation-strategy) for the validation strategy and verification record.
