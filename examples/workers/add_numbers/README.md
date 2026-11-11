# Add numbers worker

A standalone example for the `add_numbers` job type. It sums integers and finite decimal numbers, rejects booleans and strings, and returns zero for an empty list. It has no artificial delay and sends no heartbeats; computation and outcome reporting must fit within the initial lease.

For lease demonstrations, use [delay](../delay/README.md) (without heartbeat) or [delay_with_heartbeat](../delay_with_heartbeat/README.md).

## Setup

Start Orqbit and authenticate using the [quickstart](../../../docs/quickstart.md). Register a worker using `POST /workers` with your user bearer token:

```json
{"name":"add-numbers","supported_types":["add_numbers"],"permission_policy":"PRIVATE"}
```

Save the returned `secret_api_key`. From this directory, with Python 3.13 and uv installed:

```powershell
uv sync --locked
Copy-Item .env.example .env
```

Set `API_KEY` to that worker key and `API_URL` to the API address. Configuration is read from this directory's `.env`, regardless of working directory; environment variables override file values. Keep the real `.env` private.

| Setting | Default | Meaning |
| --- | --- | --- |
| `API_KEY` | Required | Registered worker's secret API key |
| `API_URL` | Required | API base URL; example uses `http://127.0.0.1:8000` |
| `POLL_INTERVAL` | 2 | Seconds between empty-queue polls |
| `REQUEST_TIMEOUT` | 10 | HTTP timeout in seconds |

Timing settings must be positive and finite.

## Run

```powershell
uv run --locked python worker.py
```

Using the same user, submit `POST /jobs/` with a fresh `Idempotency-Key` header:

```json
{"job_type":"add_numbers","params":{"numbers":[2,3,5]},"permission_policy":"PRIVATE"}
```

Read `GET /jobs/{id}` for `SUCCEEDED` and `{"sum":10}`. Invalid numbers are reported with `INVALID_PARAMS`. Register this worker for `add_numbers` only.

Ctrl+C stops the worker. HTTP or connection errors stop it with exit code 1; requests are not retried. An outcome response can be lost after the server accepted it. There is no worker-side crash recovery.

## Code and tests

- `settings.py`: validated configuration.
- `api.py`: authenticated HTTP requests and empty-queue handling.
- `worker.py`: addition, claim/execute/report, and polling loop.
- `tests/`: separate files for addition, settings, HTTP, and the worker loop.

Each example has its own dependencies and tests and can be copied without the backend or sibling workers.

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```
