# Development and verification

## Repository layout

```text
src/
  main.py                  FastAPI application; creates tables at import
  database.py              Hard-coded SQLite engine and session dependency
  models.py                Job model and status enum
  api/
    api.py                 Empty placeholder
    routers/job_router.py  Create, list, and read jobs
    routers/claim_router.py Claim, success, and failure operations
    dto/jobs.py            Job request/response models
    dto/claims.py          Worker request models
Dockerfile                 Empty placeholder
pyproject.toml             Empty placeholder
docs/                      Current status and proposed implementation design
```

## Running the existing prototype

There is no supported clean-install procedure yet. Python dependencies visible in source are FastAPI, SQLAlchemy, and Pydantic; Uvicorn is needed for the launch command. Their versions are not declared or locked. A pre-existing local virtual environment is not a distributable dependency specification.

In an environment containing those dependencies, run from the repository root:

```sh
python -m uvicorn main:app --app-dir src --reload
```

If using an existing Windows virtual environment, the equivalent interpreter invocation is:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir src --reload
```

`--app-dir src` is necessary for the current top-level imports. The reload flag is for local development. Database state currently lives in `orqbit.db` relative to the launch directory, and importing `main` creates tables. Changing the working directory changes which database file is used.

The API normally exposes interactive docs at `http://127.0.0.1:8000/docs` and its schema at `/openapi.json`. Current setup and routes are prototypes; see [status](status.md) for verification limits.

## Target environment and Compose workflow

Implement these in roadmap milestone 1; these settings and services do not exist yet:

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

As of the documentation review, only syntax, isolated in-memory schema/handler checks, and a FastAPI response-field conversion probe have been performed. There is no committed test suite. See the [verification record](status.md#verification-performed) for exact scope.

When implementing features, update the current API and status docs together, mark roadmap milestones complete only after their acceptance checks pass, and record meaningful remaining limitations.
