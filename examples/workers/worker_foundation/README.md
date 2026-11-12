# Worker foundation

A starting template for an independent Orqbit worker. Copy these files into your own worker directory:

| File | Purpose |
| --- | --- |
| `api.py` | HTTP requests authenticated with the worker's API key, including empty-queue handling. |
| `settings.py` | Local `.env` configuration, request/poll timing, and a heartbeat interval. |
| `worker.py` | Claim/process loop, logging, and process-level error handling. |
| `pyproject.toml` | Dependencies and the existing pytest/Ruff configuration. Rename the project in your copy. |
| `.env.example` | Configuration template containing no real credentials. |

This is a template, not a complete runnable worker. Its entry point expects you to provide `execution.py` with `process_attempt(settings, attempt)` and `heartbeat.py` with `LeaseLost`. Task-specific settings belong in your copy of `settings.py` and `.env.example`.

Follow [Build a worker with leases and heartbeats](../../../tutorials/worker-leases-and-heartbeats/01-create-the-worker.md) to turn the foundation into a complete worker, including lease renewal, execution logic, tests, registration, and startup.

Run `uv sync` in your new directory to create its own environment and lockfile. Keep the real `.env` private. Your worker uses its copied files; it does not import this directory, backend code, or another worker. Existing example workers remain independently runnable.
