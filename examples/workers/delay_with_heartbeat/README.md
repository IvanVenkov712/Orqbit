# Delay worker with heartbeat

A standalone `delay_with_heartbeat` worker. It waits for `EXECUTION_DELAY` seconds per claimed attempt and reports `{"waited_seconds":150}` with the default delay. Job parameters are `{}`; duration is configured on the worker.

The wait is split into steps, with bodyless authenticated heartbeats between them. Each returned `lease_expires_at` determines the next interval, capped by `HEARTBEAT_INTERVAL` and one third of the remaining lease. No background thread is needed for this waiting task.

## Setup and run

Start Orqbit and authenticate using the [quickstart](../../../docs/quickstart.md). With your user bearer token, register `POST /workers`:

```json
{"name":"delay-heartbeat","supported_types":["delay_with_heartbeat"],"permission_policy":"PRIVATE"}
```

From this directory, using Python 3.13 and uv:

```powershell
uv sync --locked
Copy-Item .env.example .env
```

Set `API_KEY` in `.env` to the returned `secret_api_key` and adjust `API_URL` as needed.

| Setting | Default | Meaning |
| --- | --- | --- |
| `API_KEY` | Required | Registered worker's secret API key |
| `API_URL` | Required | API base URL; example uses `http://127.0.0.1:8000` |
| `POLL_INTERVAL` | 2 | Seconds between empty-queue polls |
| `REQUEST_TIMEOUT` | 10 | HTTP timeout in seconds |
| `EXECUTION_DELAY` | 150 | Seconds to wait per task; zero is allowed |
| `HEARTBEAT_INTERVAL` | 10 | Maximum seconds between heartbeats |

All durations must be finite; polling, HTTP timeout, and heartbeat interval must be positive. The adjacent `.env` is read regardless of working directory; environment variables override it. Keep the real `.env` private.

```powershell
uv run --locked python worker.py
```

Using the same user, submit `POST /jobs/` with a fresh `Idempotency-Key`:

```json
{"job_type":"delay_with_heartbeat","params":{},"permission_policy":"PRIVATE"}
```

## Lease demonstration

With API settings `LEASE_SECONDS=120`, `LEASE_EXTENSION_SECONDS=60`, and the default `EXECUTION_DELAY=150`:

The worker logs lease renewals and finishes after the original 120-second lease. `GET /jobs/{id}` should show `SUCCEEDED` with `{"waited_seconds":150}`. The default heartbeat interval is 10 seconds; leave enough headroom for HTTP requests and scheduling delays and synchronize the worker host's clock with the API/database clock.

A failed heartbeat, expired local deadline, invalid renewal, or missing ownership stops the wait and exits with code 1 without sending success or failure. There are no automatic retries. The API remains authoritative if the lease expires during an outcome request.

Ctrl+C stops the worker. Other HTTP/connection errors also stop it with code 1. The worker does not recover abandoned attempts or undo accepted outcomes. Compare with [delay without heartbeat](../delay/README.md) and [add_numbers](../add_numbers/README.md).

## Code and checks

`settings.py` contains configuration and `api.py` contains HTTP access. `heartbeat.py` reads lease deadlines, checks expiry, renews ownership, and coordinates the wait. `execution.py` handles one attempt (type check, wait, outcome), while `worker.py` contains polling and startup/error handling. This directory is independently installable and does not import backend or sibling-worker code.

Tests use mocked HTTP and a virtual clock to cover execution beyond the original lease, ownership loss, and expiry; no running API or database is required.

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```
