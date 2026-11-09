# Orqbit

Orqbit is a Python backend for asynchronous job processing. Clients submit jobs over HTTP; independent workers pull compatible jobs, execute them outside the API, and report outcomes. PostgreSQL stores jobs, permissions, and execution attempts.

**Status: learning prototype.** User authentication, worker API keys, permission-aware reads, paginated lists, atomic claims, and owned success/failure reporting are implemented. Heartbeats, lease recovery, retries, and submission/acknowledgement idempotency remain planned. A crashed worker can leave a job running indefinitely. See [implementation status](docs/status.md) for the current guarantees and limitations.

## Current workflow

1. Register and log in a user to obtain a bearer token.
2. Submit a job with a type, JSON parameters, and permission policy.
3. Register a worker with supported job types and save its returned API key.
4. The worker claims an accessible pending job using `X-API-Key` and no request body.
5. The worker executes the job independently and reports by the returned **attempt ID**.
6. The client reads the job's status, result/error, and attempt IDs.

```text
PENDING -> RUNNING -> SUCCEEDED
                  \-> FAILED
```

Claims use a PostgreSQL transaction with `FOR UPDATE SKIP LOCKED`; claiming creates an attempt and marks the job running in that transaction. Outcome reports lock the attempt, check worker ownership and running status, and update job and attempt together. These operations coordinate work; the API does not execute worker handlers. An [example worker](examples/workers/add_numbers/worker.py) runs `add_numbers` jobs independently.

The [API reference](docs/api.md) covers authentication, job and worker routes, permission policies, list filters, and current errors. Interactive OpenAPI documentation is available at `/docs` while the API runs.

## Run with Docker Compose

Use the [PowerShell quickstart](docs/quickstart.md) for configuration, signing-key generation, startup, authenticated submission, and persistence across container recreation. It requires Git and Docker in Linux-container mode; host Python and PostgreSQL are unnecessary.

Compose runs PostgreSQL, an explicit Alembic migration service, and the API. `GET /health/live` checks liveness; `/health` is an alias. `GET /health/ready` requires database access, matching migration heads, and queryable mapped tables/columns. Health checks never apply migrations. The named database volume survives ordinary `docker compose down`.

## Run Python on your host

Use Python 3.13 and uv. Create a PostgreSQL database named `orqbit`, then run from the repository root:

```powershell
cd backend
uv sync --locked
Copy-Item .env.example .env
uv run --locked python -c "import secrets; print(secrets.token_hex(32))"
```

Edit `backend/.env`: set `DATABASE_URL` to your local credentials and replace `SECRET_KEY=replace_with_secret_key` with the generated 64-character hexadecimal value. Keep `ALGORITHM=HS256` and a positive `ACCESS_TOKEN_EXPIRE_MINUTES`. `LEASE_SECONDS` and `PROTRACTION_SECONDS` must also be positive, although lease/heartbeat behavior is not implemented. The real environment files are ignored by Git. Continue running the following Python commands from `backend/`; run Docker Compose commands from the repository root.

```powershell
uv run --locked alembic upgrade head
uv run --locked uvicorn main:app --app-dir src --reload
```

The API defaults to `http://127.0.0.1:8000`. Importing the app does not create tables. See [development](docs/development.md) for configuration and existing-database migration notes, and [testing](docs/testing.md) for PostgreSQL test setup and CI commands.

## Example: add_numbers worker

The example worker is a standalone Python application with its own `pyproject.toml`, `uv.lock`, virtual environment, configuration, and tests. You can copy `examples/workers/add_numbers/` to another machine without the backend source or settings. It communicates only through the HTTP API; a running API and registered worker key are required to process jobs.

It claims jobs, sums `params.numbers`, and reports a result such as `{"sum":10}` for `{"numbers":[2,3,5]}`. It accepts integers and finite decimal numbers, rejects booleans and strings, and returns zero for an empty list. Invalid parameters are reported as failed attempts.

Start the API and register/log in a user using the [quickstart](docs/quickstart.md). In `/docs`, authorize with that user's bearer token and create a worker with `POST /workers`:

```json
{"name":"add-numbers","supported_types":["add_numbers"],"permission_policy":"PRIVATE"}
```

Save the returned `secret_api_key`. From the repository root:

```powershell
cd examples/workers/add_numbers
uv sync --locked
Copy-Item .env.example .env
```

Edit `examples/workers/add_numbers/.env`, setting `API_KEY` to that worker key and `API_URL` to the API address (default local address: `http://127.0.0.1:8000`). `POLL_INTERVAL` controls the seconds between empty-queue polls (default 2); `REQUEST_TIMEOUT` controls the HTTP timeout in seconds (default 10). Both must be positive. The worker always reads its adjacent `.env`, regardless of working directory; environment variables override file values. The real `.env` is ignored by Git.

Run the worker with Python 3.13 in a separate terminal from `examples/workers/add_numbers/`:

```powershell
uv run --locked python worker.py
```

Run its tests and checks from the same directory, without starting the API or PostgreSQL:

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Using the same user, submit `POST /jobs/` with a unique `Idempotency-Key` header and this body:

```json
{"job_type":"add_numbers","params":{"numbers":[2,3,5]},"permission_policy":"PRIVATE"}
```

Read `GET /jobs/{id}` to see `SUCCEEDED` and `{"sum":10}`. Worker capabilities are registered on the server; register this example for `add_numbers` only. Stop with Ctrl+C. HTTP/connection errors stop the worker with a nonzero exit code; there are no automatic request retries or crash recovery. A stopped worker can leave an attempt running, including when an outcome response is lost.

## Documentation

- [Status and limitations](docs/status.md): implemented behavior and verification evidence.
- [API](docs/api.md): current requests, authentication, permissions, and responses.
- [Quickstart](docs/quickstart.md): runnable Docker and PowerShell demonstration.
- [Development](docs/development.md): repository layout, configuration, migrations, and containers.
- [Testing](docs/testing.md): integration coverage and the separate Compose smoke check.
- [Roadmap](docs/roadmap.md): completed foundations and remaining work.
- [Architecture](docs/architecture.md) and [requirements](docs/requirements.md): future reliability proposals, including leases, retries, and idempotency.

There is no exactly-once execution guarantee. Future retries will require idempotent worker side effects; submission deduplication alone cannot prevent a worker from repeating an external action.

## License

[MIT](LICENSE).
