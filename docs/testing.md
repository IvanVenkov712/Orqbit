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

### What is tested and why

The pytest suite covers the current authenticated API and attempt-based outcomes. Its sources are [job tests](../backend/tests/test_jobs.py), [concurrent claim tests](../backend/tests/test_concurrent_claims.py), [health tests](../backend/tests/test_health.py), and [migration tests](../backend/tests/test_migrations.py). The [Compose smoke check](../backend/tests/compose_smoke.py) runs separately.

| Area | What is checked | Why |
| --- | --- | --- |
| Create and read jobs | Creation returns an ID, `PENDING`, and empty result/error fields. A later HTTP request and a separate database session retrieve the saved job. | Confirm that accepted jobs are committed and available after the original request ends. |
| Submission idempotency | Required keys are validated, stored with request fingerprints, and scoped to the creator. Matching sequential/concurrent requests return one job; changed content returns 409. Object-key and permission-list normalization are checked. | Allow safe submission retries without merging distinct intended jobs or hiding unrelated integrity errors. |
| JSON persistence | Nested objects, arrays, Unicode, booleans, numbers, and null survive database storage and response serialization. Results and errors also round-trip. | Catch input/output corruption between JSON, PostgreSQL JSONB, and the API. |
| Invalid or absent resources | Missing required fields and wrong input types return 422 without inserting a job. PostgreSQL data errors from oversized IDs or null characters return generic 422 responses, including on outcomes, without changing persisted state. Missing jobs and an empty claim queue return 404. | Reject malformed submissions and avoid turning invalid storage values into HTTP 500 responses. |
| Claim eligibility | Only an accessible, compatible pending job is selected using the worker's stored supported types; request bodies cannot override them. The response identifies both the job and its new running attempt. | Avoid assigning unsupported or inaccessible work, or selecting an already running job. |
| Leases and heartbeats | Initial claim deadlines are bounded by PostgreSQL timestamps even when the model's local clock is skewed. Renewal returns the persisted deadline, extends a short lease, preserves a longer lease, and leaves job data unchanged. Missing credentials, wrong ownership, terminal status, and expired leases are rejected. New success/failure reports after expiry leave job and attempt unchanged; exact accepted outcome replays remain valid after the deadline. | Verify the public lease protocol, shared clock, and rejection of stale updates. |
| Heartbeat/outcome contention and expiry | A request holds its attempt lock after flush while another heartbeat or outcome waits. Tests exercise both orders with success and failure. Another test expires a lease while heartbeat/success/failure waits for its row lock, then verifies rejection using fresh database time. PostgreSQL `pg_blocking_pids()` confirms actual blocking; events and bounded waits replace arbitrary sleeps. | Prevent renewal from reviving a terminal attempt or accepting a report based on the transaction's older timestamp. |
| Concurrent claims and rollback | One claim is held after its database flush while a different worker claims through another client/session. With one job, the second worker gets 404; with two, it receives the next job. Both cases verify persisted attempt ownership and distinct assignments. An injected failure after flush rolls back the job update and attempt insert, allowing another worker to claim. | Exercise PostgreSQL row locking and atomic persistence with deliberate overlap, bounded waits, and no sleeps. The second request must finish before the first transaction is released. |
| Authentication and permissions | Job endpoints require a user token; claims require a valid, active worker API key. Permission policies control reads, lists, and claims, including explicit user and worker grants. List filters and pagination are checked. | Keep private jobs hidden and verify that policy-specific grants apply only where allowed. |
| Worker types and list loading | Worker types use the same nonblank, 1–100 character rules as job types. A list containing multiple jobs loads their attempts in one query. | Reject unusable capabilities and prevent a query per job during serialization. |
| Outcomes and transitions | The owning worker reports by attempt ID. Success/failure updates both job and attempt. Exact accepted replays return 200 without changing values or timestamps; conflicting/lost-attempt reports return 409. Missing or another worker's attempts return 404. Missing credentials and malformed outcomes are rejected without changing state. | Record worker outcomes, permit safe acknowledgement retries, and prevent unauthorized or conflicting updates. |
| Attempt history | Authorized reads return attempt details, worker attribution, timestamps, and outcomes ordered by descending attempt number. Pagination, empty histories, validation, and missing/inaccessible jobs are checked. | Expose persisted execution records without bypassing job permissions or mixing histories between jobs. |
| Timestamps | Creation/update timestamps are UTC-aware. Claiming and reporting an outcome advance `updated_at` while preserving `created_at`; exact outcome replays preserve timestamps. | Keep job chronology meaningful. Tests seed an old timestamp instead of sleeping, inspect PostgreSQL, and check timestamps exposed by attempt history. |
| Migrations | Alembic prepares the current PostgreSQL schema and permission enums, including creator-scoped submission-key uniqueness. Repeated upgrades preserve jobs. Downgrade/reupgrade removes and restores the new model; legacy jobs acquire an inactive private owner and synthetic submission keys. The lease migration preserves terminal attempt fields and backfills deadlines from `updated_at` before enforcing `NOT NULL`. Legacy running jobs/attempts cause transactional upgrade failures without partial changes. | Check first-time setup, safe reruns, and explicit treatment of historical ownership, submission keys, and lease deadlines. |
| Liveness and readiness | Healthy PostgreSQL produces ready=200. A refused connection, absent migration records, outdated revision, missing table/column in any mapped table, or blocked schema query produces ready=503. Liveness stays at 200; readiness returns to 200 after repair. | Verify dependencies for authentication, permissions, attempts, workers, and jobs, while keeping database details out of responses. |
| Containers and persistence | Compose builds and starts the stack; the runtime is non-root and excludes `.env` files and selected development tools. A job survives repeated migrations, a real database outage, and container recreation with the volume retained. | Catch packaging/startup problems and verify that container lifecycle changes preserve stored jobs. Database outage recovery here means reconnecting to PostgreSQL, not recovering abandoned running jobs. |

Real PostgreSQL checks JSONB, enums, transactions, and schema behavior that SQLite cannot faithfully verify. Temporary schemas and per-test cleanup prevent one case's data from affecting another; real commits and separate sessions ensure assertions do not rely only on objects cached in memory.

Run the other CI checks locally from `backend/` with:

```powershell
uv run --locked ruff check .
uv run --locked python -m compileall -q src migrations tests
```

GitHub Actions runs on pushes and pull requests with Python 3.13 and a healthy PostgreSQL 18 service. It installs locked dependencies, runs these checks, and runs pytest, whose fixture applies Alembic migrations. A separate job builds and exercises the Compose stack, including readiness during a database outage and persistence across container recreation. CI database credentials exist only for temporary services. The pytest cases exercise concurrent claim exclusivity and attempt ownership; they do not establish abandoned-job recovery or exactly-once execution.

## Docker Compose smoke check

An automated smoke check runs the complete flow in its own randomly named project with generated test credentials, a generated JWT signing key, and a temporary database volume. It builds the image, waits for readiness, checks that the runtime excludes secrets and development tools, registers and logs in a user, creates/reads a private job using its bearer token, reruns migrations, stops PostgreSQL to verify live=200/ready=503, starts PostgreSQL again to verify recovery, recreates the containers while retaining the volume, and reads the same job. It removes only its own containers and volume afterward. Run it from the repository root (`cd ..` if you are in `backend/`):

```powershell
python backend/tests/compose_smoke.py
# Choose another local port if 18000 is occupied:
python backend/tests/compose_smoke.py --port 18001
```

The smoke script uses only Python's standard library and Docker Compose; a host virtual environment or `.env` file is not required. It runs as a separate GitHub Actions job.

## Validation strategy

The scenarios below guide tests for future features. They extend the implemented coverage above; they are not current guarantees.

Add unit tests for retry calculation and error classification. Extend the real PostgreSQL integration tests to cover retry scheduling, attempt-generation fencing after reassignment, and recovery. SQLite tests alone cannot validate PostgreSQL locking behavior.

Add competing success/failure report tests beyond the existing heartbeat/outcome contention tests. For resilience tests, kill a worker after claim and after an external effect, lose acknowledgement responses, race heartbeats with the future recovery/reassignment process, run multiple recovery instances, and restart services while work is active.

For a future recovery acceptance demonstration: renew a claimed attempt's lease; kill the worker; observe an expired attempt and delayed retry; finish with a second worker; inspect both attempts and creator attribution; verify that the first worker's late completion is rejected. Repeat across a service restart. Lease renewal and rejection of expired reports are implemented; automatic expiry processing, reassignment, and retries remain planned.

## Verification record

On 2026-11-11, all **256 backend tests passed**, using real PostgreSQL for integration coverage; Ruff, formatting of the changed job tests, syntax compilation, and diff checks also passed. Compose configuration was validated with the example lease window and an environment override. The container smoke check could not run because the Docker daemon was unavailable; the manual Docker quickstart was not rerun. See the [status verification record](status.md#verification-performed) for the exact test command and earlier verification history. This documentation-only follow-up does not rerun the backend suite.

Remove completed roadmap items only after their relevant acceptance checks pass. Add focused coverage for new behavior using this setup; do not treat the future scenarios above as already tested guarantees.
