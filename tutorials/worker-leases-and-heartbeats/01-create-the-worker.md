# 1. Create an independent worker

[Tutorial home](README.md) · [Next: Implement heartbeats →](02-implement-heartbeats.md)

We will copy the [worker foundation](../../examples/workers/worker_foundation/README.md), then write the lease-handling and task code ourselves. Everything will live in `examples/workers/delayed_greeting/`. This directory must be new; do not overwrite an existing worker.

## Copy the small foundation

From the **repository root**, in PowerShell:

```powershell
New-Item -ItemType Directory -Path examples/workers/delayed_greeting
Copy-Item -Path examples/workers/worker_foundation/api.py, examples/workers/worker_foundation/settings.py, examples/workers/worker_foundation/worker.py, examples/workers/worker_foundation/pyproject.toml, examples/workers/worker_foundation/.env.example -Destination examples/workers/delayed_greeting
cd examples/workers/delayed_greeting
```

On macOS or Linux:

```sh
mkdir examples/workers/delayed_greeting
cp examples/workers/worker_foundation/api.py examples/workers/worker_foundation/settings.py examples/workers/worker_foundation/worker.py examples/workers/worker_foundation/pyproject.toml examples/workers/worker_foundation/.env.example examples/workers/delayed_greeting/
cd examples/workers/delayed_greeting
```

In your copied `pyproject.toml`, change the project name to:

```toml
name = "orqbit-delayed-greeting-worker"
```

The copied `worker.py` already has a generic startup message. Keep it unchanged. The job-type check will be in `execution.py` in step 3.

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

Your copied `settings.py` contains connection, polling, and heartbeat settings. Our demonstration also needs a task duration. Add this field inside its `Settings` class:

```python
    execution_delay: float = Field(default=150, ge=0, allow_inf_nan=False)
```

`Field` is already imported. Add `EXECUTION_DELAY=150` to your copied `.env.example`, so it contains:

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
