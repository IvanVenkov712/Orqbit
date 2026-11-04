# Orqbit

Orqbit is an asynchronous job processing platform: clients submit jobs, and workers pull jobs they know how to execute. The intended design uses PostgreSQL for durable queue state, worker leases, retries, idempotency, and execution history.

**Status: early prototype.** Job submission, retrieval, claiming by type, success/failure reporting, PostgreSQL configuration, and Alembic migrations exist. Authentication, heartbeats, recovery, retries, idempotency, and attempt history are still planned. Concurrent claiming is currently unsafe. See the [implementation status and known problems](docs/status.md) before running multiple workers.

## Intended capabilities

- Client API to submit jobs and inspect their status and results.
- Worker API to claim pending jobs by supported type.
- Authenticated creator identity and worker ownership of each execution attempt.
- Worker heartbeats and per-attempt leases to recover abandoned jobs.
- Bounded retries with backoff and a terminal failure state.
- PostgreSQL persistence with versioned database migrations.
- Docker Compose for a repeatable local environment.
- Idempotent submission and safe retries of worker acknowledgements.
- A durable record of every execution attempt, including its worker and outcome.

Orqbit is intended to provide **at-least-once execution**. Workers must make external side effects idempotent: a worker can finish an action and crash before reporting success. An idempotency key on job submission alone cannot prevent that duplicate action.

## Current implementation

The repository uses Python, FastAPI, Pydantic, and synchronous SQLAlchemy sessions with PostgreSQL. Workers execute application-specific job handlers outside the API process; no worker executable or SDK is included yet.

| Method | Route | Behavior today |
| --- | --- | --- |
| POST | `/jobs/` | Create a pending job |
| GET | `/jobs` | List all jobs, without pagination |
| GET | `/jobs/{job_id}` | Read a job |
| POST | `/workers/claim` | Claim the oldest matching pending job by ID |
| POST | `/workers/{job_id}/succeed` | Mark a running job successful |
| POST | `/workers/{job_id}/fail` | Mark a running job failed |

These are prototype routes. They do not authenticate callers or enforce worker ownership. A failed job remains failed; it is not retried automatically. Request examples and current response behavior are in the [API documentation](docs/api.md).

## Running the prototype

Use Python 3.13 and uv. With PostgreSQL running and an empty `orqbit` database already created, run from the repository root:

```powershell
uv sync --locked
Copy-Item .env.example .env
```

Edit `.env` with your local PostgreSQL credentials. The example credentials are for local development; supply credentials through the environment in production. The real `.env` is ignored by Git. Then run:

```powershell
uv run --locked alembic upgrade head
uv run --locked uvicorn main:app --app-dir src --reload
```

The server defaults to `http://127.0.0.1:8000`; interactive API documentation is available at `/docs`. Importing the app does not create tables; migrations are an explicit step. Container setup remains unfinished.

PostgreSQL integration tests and the GitHub Actions workflow are included. See [development and verification](docs/development.md#postgresql-integration-tests) for test database setup and commands.

## Documentation

- [Status and current problems](docs/status.md): what exists, what is missing, and verification evidence.
- [Architecture and reliability](docs/architecture.md): proposed data model, ownership, leases, retries, and idempotency.
- [API](docs/api.md): existing endpoints and proposed contract changes.
- [Implementation roadmap](docs/roadmap.md): dependency-ordered milestones and acceptance criteria.
- [Requirements](docs/requirements.md): functional scope, non-functional requirements, and important additions.
- [Development](docs/development.md): repository layout, launch limitations, and validation strategy.

The status and current API sections describe existing code. Target designs and roadmap items are proposals, not implemented behavior.

## Recommended next step

Establish a reproducible PostgreSQL development environment with migrations and CI. Then add authenticated identities and attempt records before implementing atomic claims, lease recovery, and retries. Submission idempotency should ship with the first usable client API. The [roadmap](docs/roadmap.md) gives the full order and release gates.

## License

[MIT](LICENSE).
