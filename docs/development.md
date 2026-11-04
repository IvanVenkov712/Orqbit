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

See the [testing guide](testing.md) for database setup, commands, coverage, and CI checks.

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

For the automated container check, see the [Compose smoke check](testing.md#docker-compose-smoke-check).

There is no recovery executable or service yet. The PostgreSQL health check and migration dependency control initial startup; the API health check continues checking database/schema readiness after startup. An unhealthy container is reported as such; Docker Compose does not automatically restart it solely because a health check fails.

## Validation strategy

See the [testing guide](testing.md#validation-strategy) for the validation strategy and verification record.
