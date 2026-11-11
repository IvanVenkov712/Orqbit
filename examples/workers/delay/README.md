# Delay worker

A standalone `delay` worker. It waits for `EXECUTION_DELAY` seconds per claimed attempt and reports `{"waited_seconds":150}` with the default delay. Job parameters are `{}`; duration is configured on the worker.

This example sends no heartbeats. A delay longer than the initial lease demonstrates that the API rejects a late outcome.

## Setup and run

Start Orqbit and authenticate using the [quickstart](../../../docs/quickstart.md). With your user bearer token, register `POST /workers`:

```json
{"name":"delay","supported_types":["delay"],"permission_policy":"PRIVATE"}
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

All durations must be finite; polling, HTTP timeout must be positive. The adjacent `.env` is read regardless of working directory; environment variables override it. Keep the real `.env` private.

```powershell
uv run --locked python worker.py
```

Using the same user, submit `POST /jobs/` with a fresh `Idempotency-Key`:

```json
{"job_type":"delay","params":{},"permission_policy":"PRIVATE"}
```

## Lease demonstration

With API settings `LEASE_SECONDS=120`, `LEASE_EXTENSION_SECONDS=60`, and the default `EXECUTION_DELAY=150`:

The worker waits 150 seconds, then its success report is rejected with HTTP 400 because the lease expired. It logs the status and exits with code 1, without retrying or sending a failure report. To see a successful short task, set `EXECUTION_DELAY=5` and submit a new job.

Rejecting an expired report does not itself update the stored job or attempt status.

Ctrl+C stops the worker. Other HTTP/connection errors also stop it with code 1. The worker does not recover abandoned attempts or undo accepted outcomes. Compare with [delay with heartbeat](../delay_with_heartbeat/README.md) and [add_numbers](../add_numbers/README.md).

## Code and checks

`settings.py` contains configuration, `api.py` contains HTTP access, `execution.py` handles one attempt (type check, delay, outcome), and `worker.py` contains polling and startup/error handling. This directory is independently installable and does not import backend or sibling-worker code.

Tests use mocked HTTP; no running API or database is required.

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```
