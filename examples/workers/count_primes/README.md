# Count primes worker

Counts prime numbers from 2 through `params.limit`, inclusive. This is a real CPU task, processed in bounded batches with cooperative heartbeat checks between batches.

## Setup and run

Start Orqbit and authenticate using the [quickstart](../../../docs/quickstart.md). Register a worker with your user bearer token using `POST /workers`:

```json
{"name":"count-primes","supported_types":["count_primes"],"permission_policy":"PRIVATE"}
```

From this directory, with Python 3.13 and uv installed:

```powershell
uv sync --locked
Copy-Item .env.example .env
```

Set `API_KEY` to the returned `secret_api_key` and adjust `API_URL`. The adjacent `.env` is read regardless of working directory; environment variables override it. Keep the real `.env` private.

| Setting | Default | Meaning |
| --- | --- | --- |
| `API_KEY` | Required | Registered worker's secret API key |
| `API_URL` | Required | API base URL; example uses `http://127.0.0.1:8000` |
| `POLL_INTERVAL` | 2 | Seconds between empty-queue polls |
| `REQUEST_TIMEOUT` | 10 | HTTP timeout in seconds |
| `BATCH_SIZE` | 1000 | Candidates processed before checking ownership; integer from 1 to 10000 |
| `HEARTBEAT_INTERVAL` | 10 | Maximum target interval between heartbeats, in seconds |

Polling, HTTP timeout, and heartbeat interval must be positive and finite.

```powershell
uv run --locked python worker.py
```

Using the same user, submit `POST /jobs/` with a fresh `Idempotency-Key`:

```json
{"job_type":"count_primes","params":{"limit":100},"permission_policy":"PRIVATE"}
```

Read `GET /jobs/{id}` for `SUCCEEDED` and `{"limit":100,"count":25}`. `limit` must be an integer from 0 to 100000000; booleans, fractional numbers, and strings are rejected with `INVALID_PARAMS`. Limits 0 and 1 produce a count of zero. Register this worker for `count_primes` only.

## Heartbeats and ownership

The worker checks the initial lease before computing, then checks ownership after every batch and before reporting. It schedules renewal using the returned `lease_expires_at`: the next target interval is the smaller of `HEARTBEAT_INTERVAL` and one third of the remaining lease. Each successful heartbeat supplies the next deadline.

Use a larger limit, such as 10000000, to observe real computation and lease renewal. Duration depends on the CPU; to demonstrate work beyond the initial lease, choose a limit and API `LEASE_SECONDS` that make the computation outlast that initial window. Leave sufficient `LEASE_EXTENSION_SECONDS` for request and processing delays. Tests verify this boundary deterministically with a virtual clock.

Cancellation is cooperative: the current batch finishes before ownership is checked. A smaller `BATCH_SIZE` reduces time between checks; no thread or background executor is involved. If a batch itself outlasts the lease, execution stops rather than reviving it. Keep the worker host's clock synchronized with the API/database clock.

A rejected or failed heartbeat, invalid deadline, or expired lease stops computation with exit code 1 and sends no success or failure report. Invalid task parameters are reported as failures. Other HTTP/connection errors also stop the worker without retrying; a lost outcome response may follow an accepted outcome. Ctrl+C stops the worker. There is no worker-side recovery or retry policy.

## Code and checks

- `primes.py`: parameter validation, primality test, and cumulative batches.
- `heartbeat.py`: deadline validation, expiry checks, and renewal.
- `execution.py`: batch execution with heartbeats and outcome reporting.
- `worker.py`: claim loop, startup, and process-level errors.
- `settings.py` and `api.py`: configuration and authenticated HTTP.
- `tests/`: separate files for computation, leases, execution, HTTP, settings, and polling.

Each worker is independently installable using only its own directory. It imports neither backend nor sibling-worker code. Tests use mocked HTTP and require no running API or PostgreSQL.

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```
