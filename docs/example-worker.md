# Example: add_numbers worker

The [example worker](../examples/workers/add_numbers/worker.py) is a standalone Python application with its own `pyproject.toml`, `uv.lock`, virtual environment, configuration, and tests. You can copy `examples/workers/add_numbers/` to another machine without the backend source or settings. It communicates only through the HTTP API; a running API and registered worker key are required to process jobs.

It claims jobs, sums `params.numbers`, and reports a result such as `{"sum":10}` for `{"numbers":[2,3,5]}`. It accepts integers and finite decimal numbers, rejects booleans and strings, and returns zero for an empty list. Invalid parameters are reported as failed attempts.

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

Edit `examples/workers/add_numbers/.env`, setting `API_KEY` to that worker key and `API_URL` to the API address (default local address: `http://127.0.0.1:8000`). `POLL_INTERVAL` controls the seconds between empty-queue polls (default 2); `REQUEST_TIMEOUT` controls the HTTP timeout in seconds (default 10). Both must be positive. The worker always reads its adjacent `.env`, regardless of working directory; environment variables override file values. The real `.env` is ignored by Git.

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

## Tests and checks

Run its tests and checks from `examples/workers/add_numbers/`, without starting the API or PostgreSQL:

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```
