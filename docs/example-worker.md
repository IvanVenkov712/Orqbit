# Example: add_numbers worker

The [example worker](../examples/workers/add_numbers/worker.py) is a standalone Python application with its own `pyproject.toml`, `uv.lock`, virtual environment, configuration, and tests. You can copy `examples/workers/add_numbers/` to another machine without the backend source or settings. It communicates only through the HTTP API; a running API and registered worker key are required to process jobs.

It claims jobs, sums `params.numbers`, and reports a result such as `{"sum":10}` for `{"numbers":[2,3,5]}`. It accepts integers and finite decimal numbers, rejects booleans and strings, and returns zero for an empty list. Invalid parameters are reported as failed attempts.

While executing `add_numbers`, a background thread sends bodyless `POST /workers/{attempt_id}/heartbeat` requests with the worker key. It uses `lease_expires_at` from claim and every renewal to schedule the next heartbeat after at most one third of the remaining lease, capped by `HEARTBEAT_INTERVAL` (default 10 seconds). This supports work lasting longer than the initial lease; see the [heartbeat protocol](api.md#attempt-heartbeats-and-leases). Keep the worker host's clock synchronized with the API/database clock.

If a heartbeat fails (including HTTP 400 for an expired/non-running attempt, 404 for missing ownership, authentication errors, or a connection timeout), the worker stops with exit code 1 and logs that ownership could not be confirmed and the outcome was discarded. It sends neither success nor failure and does not retry. The simulated delay is interrupted immediately; a handler already executing finishes locally and its result/error is discarded. Python threads cannot forcibly cancel an arbitrary handler or undo its external side effects: real handlers need cooperative cancellation and appropriate safeguards around side effects. The heartbeat thread is stopped and joined before outcome reporting, and an already expired local deadline also prevents reporting. The API remains authoritative if expiry occurs during the report request.

## Register and configure

Start the API and register/log in a user using the [quickstart](quickstart.md). In `/docs`, authorize with that user's bearer token and create a worker with `POST /workers`:

```json
{"name":"add-numbers","supported_types":["add_numbers"],"permission_policy":"PRIVATE"}
```

Save the returned `secret_api_key`. From the repository root:

```powershell
cd examples/workers/add_numbers
uv sync --locked
Copy-Item .env.example .env
```

Edit `examples/workers/add_numbers/.env`, setting `API_KEY` to that worker key and `API_URL` to the API address (default local address: `http://127.0.0.1:8000`). `POLL_INTERVAL` controls the seconds between empty-queue polls (default 2); `REQUEST_TIMEOUT` controls the HTTP timeout in seconds (default 10); `HEARTBEAT_INTERVAL` caps the seconds between attempt heartbeats (default 10). These must be positive and finite. Allow ample lease headroom for HTTP requests and scheduling delays. `EXECUTION_DELAY` optionally simulates slow work before summing (default 0 seconds, nonnegative and finite). The worker always reads its adjacent `.env`, regardless of working directory; environment variables override file values. The real `.env` is ignored by Git.

## Run and submit a job

Run the worker with Python 3.13 in a separate terminal from `examples/workers/add_numbers/`:

```powershell
uv run --locked python worker.py
```

Using the same user, submit `POST /jobs/` with a unique `Idempotency-Key` header and this body:

```json
{"job_type":"add_numbers","params":{"numbers":[2,3,5]},"permission_policy":"PRIVATE"}
```

Read `GET /jobs/{id}` to see `SUCCEEDED` and `{"sum":10}`. Worker capabilities are registered on the server; register this example for `add_numbers` only. Stop with Ctrl+C. HTTP/connection errors stop the worker with a nonzero exit code; there are no automatic request retries or crash recovery. A stopped worker can leave an attempt running, including when an outcome response is lost.

## Try execution beyond the initial lease

With the API example configuration (`LEASE_SECONDS=120`, `LEASE_EXTENSION_SECONDS=60`), start the worker with a 150-second simulated task:

```powershell
$env:EXECUTION_DELAY = "150"
$env:HEARTBEAT_INTERVAL = "10"
uv run --locked python worker.py
```

Submit the same job body above with a fresh `Idempotency-Key`. While the job is `RUNNING`, the worker logs `Renewed lease for attempt ... until ...`. After at least 150 seconds, beyond the original 120-second lease, it reports success; `GET /jobs/{id}` should return `SUCCEEDED` and `{"sum":10}`. If your API uses a different initial lease, choose a delay longer than `LEASE_SECONDS`. After stopping the worker, remove the overrides with `Remove-Item Env:EXECUTION_DELAY` and `Remove-Item Env:HEARTBEAT_INTERVAL`.

The worker tests reproduce this boundary deterministically with a virtual clock, exercise repeated renewal using a shorter extension window, and verify that ownership loss during either the delay or handler prevents both outcome reports.

## Tests and checks

Run its tests and checks from `examples/workers/add_numbers/`, without starting the API or PostgreSQL:

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```
