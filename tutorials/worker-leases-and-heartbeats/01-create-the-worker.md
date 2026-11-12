# 1. Create an independent worker

[Tutorial home](README.md) · [Next: Implement heartbeats →](02-implement-heartbeats.md)

We will reuse the example's HTTP client, settings, and polling loop, then write the lease-handling and task code ourselves. Everything will live in `examples/workers/delayed_greeting/`. This directory must be new; do not overwrite an existing worker.

## Copy the small foundation

From the **repository root**, in PowerShell:

```powershell
New-Item -ItemType Directory -Path examples/workers/delayed_greeting
Copy-Item -Path examples/workers/delay_with_heartbeat/api.py, examples/workers/delay_with_heartbeat/settings.py, examples/workers/delay_with_heartbeat/worker.py, examples/workers/delay_with_heartbeat/pyproject.toml, examples/workers/delay_with_heartbeat/.env.example -Destination examples/workers/delayed_greeting
cd examples/workers/delayed_greeting
```

On macOS or Linux:

```sh
mkdir examples/workers/delayed_greeting
cp examples/workers/delay_with_heartbeat/api.py examples/workers/delay_with_heartbeat/settings.py examples/workers/delay_with_heartbeat/worker.py examples/workers/delay_with_heartbeat/pyproject.toml examples/workers/delay_with_heartbeat/.env.example examples/workers/delayed_greeting/
cd examples/workers/delayed_greeting
```

In your copied `pyproject.toml`, change the project name to:

```toml
name = "orqbit-delayed-greeting-worker"
```

In your copied `worker.py`, replace `delay_with_heartbeat` with `delayed_greeting` in its introductory description and startup log. Keep the rest of the file unchanged. The job-type check itself will be in `execution.py` in step 3.

Install the worker's dependencies:

```powershell
uv sync
```

This creates its own `.venv` and `uv.lock`. Later commands use `--locked` to keep those dependency versions. You do not need the backend's environment or database credentials.

## Understand the files you reused

| File | Responsibility |
| --- | --- |
| `api.py` | Sends HTTP POST requests using `X-API-Key`. A claim returns an attempt; the exact empty-queue response, 404 with `No jobs were found`, becomes `None`. Other errors propagate. |
| `settings.py` | Reads this directory's `.env`, validates URLs and timing values, and keeps the API key out of error output. |
| `worker.py` | Claims one job at a time, delegates to `process_attempt`, and waits only when the queue is empty. Catches `LeaseLost`, logs it, and exits with code 1. |

We will add `heartbeat.py` and `execution.py` next. Until then, starting `worker.py` will fail because those imports are not yet available.

## Know your settings

Your copied `.env.example` already contains:

```dotenv
API_KEY=replace_with_worker_secret_api_key
API_URL=http://127.0.0.1:8000
POLL_INTERVAL=2
REQUEST_TIMEOUT=10
EXECUTION_DELAY=150
HEARTBEAT_INTERVAL=10
```

Keep the example as a template. You will create the private `.env` and add a real key in step 5. `EXECUTION_DELAY` controls our demonstration task's duration. `HEARTBEAT_INTERVAL` caps the time between renewals while waiting. Terminal environment variables override the file.

The server separately controls the lease duration. A worker setting does not extend it by itself.

[Continue to step 2 →](02-implement-heartbeats.md)
