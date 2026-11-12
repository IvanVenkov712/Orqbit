# Add numbers console producer

A continuously running, standalone producer. Each console line submits a separate `add_numbers` job. A background thread submits queued lines and checks for completed jobs, allowing you to keep typing while workers execute earlier submissions.

## Setup

Start Orqbit with its current database migrations applied and authenticate using the [quickstart](../../../docs/quickstart.md). With your user bearer token, register a producer using `POST /producers`:

```json
{"name":"numbers-console"}
```

Save its returned `secret_api_key`. Start the [add_numbers worker](../../workers/add_numbers/README.md) under the same user: this producer submits `PRIVATE` jobs.

From this directory, with Python 3.13 and uv installed:

```powershell
uv sync
Copy-Item .env.example .env
```

Set `API_KEY` to the producer's secret API key and `API_URL` to the API address. Edit an existing `.env` rather than overwriting it. The adjacent `.env` is loaded regardless of working directory; environment variables override file values.

| Setting | Default | Meaning |
| --- | --- | --- |
| `API_KEY` | Required | Registered producer's secret API key |
| `API_URL` | Required | API base URL, e.g. `http://127.0.0.1:8000` |
| `POLL_INTERVAL` | 2 | Seconds between background processing cycles |
| `REQUEST_TIMEOUT` | 10 | Per-request HTTP timeout in seconds |

Timing values must be positive and finite. Keep the real `.env` private.

## Run

```powershell
uv run python producer.py
```

Enter numbers separated by spaces, pressing Enter after each job:

```text
2 3 4 8
6 7 9 3
```

These are two different jobs. You can keep entering lines while waiting for their results. Accepted submissions print their job IDs; successful outcomes appear once each, on separate lines:

```text
Submitted job 42.
Submitted job 43.
2 + 3 + 4 + 8 = 17
6 + 7 + 9 + 3 = 25
```

Results appear in the order completion is observed, which may differ from submission order. The sum comes from the worker's stored result. Failed jobs print their job ID and stored error once. Blank lines are ignored; invalid input prints a message and lets you try again. Integers, finite decimals, negative numbers, and exponent notation are accepted; booleans, strings, NaN, and infinity are rejected.

Press **Ctrl+C** to stop (exit code 130). End-of-input also stops the program (exit code 0). Shutdown signals the background thread and waits up to `REQUEST_TIMEOUT` seconds for an in-flight request. Already submitted jobs continue independently in Orqbit.

## Processing and idempotency

The main thread validates console input and puts each line into an in-memory queue with a fresh UUID idempotency key. A single background thread owns the pending submissions and active job IDs. Each cycle:

1. Collect queued lines.
2. Submit new and retryable requests with `POST /producer/jobs`, `X-API-Key`, and the saved `Idempotency-Key`.
3. Read each active job through `GET /producer/jobs/{job_id}`.
4. Print terminal outcomes and remove those jobs from the tracked set.
5. Wait `POLL_INTERVAL` seconds, or stop early when shutdown is signalled.

The default wait is two seconds. HTTP requests are sequential within the background thread, so a cycle also takes the time required for its requests; it is not a hard two-second completion notification guarantee. New console lines are sent in the next cycle. Tracking is limited to jobs submitted during this process; existing producer jobs are not scanned.

The application manages keys automatically. If a submission response is lost, or the server returns HTTP 408, 429, or 5xx, it retries in a later cycle with the **same key and numbers**. A matching replay returns the existing job. Other HTTP submission errors, such as 401, 409, or 422, reject that line and print the HTTP status. Status-read errors retain the active job for a later check. Error diagnostics omit raw HTTP response bodies and credentials.

Entering the same numbers on another line intentionally creates a new job with a new key. Keys and tracked submissions live only in memory: stopping or crashing the program loses unsent lines, uncertain submissions, and local tracking. There is no automatic recovery across restarts. The server keeps accepted jobs, and the owner can inspect them through Orqbit.

## Code and tests

- `producer.py`: console validation, automatic keys, input queue, background processing, and shutdown.
- `api.py`: producer HTTP requests through the Python standard library.
- `settings.py`: validated configuration.
- `tests/test_producer.py`: focused HTTP, input, idempotency, polling, concurrency, and shutdown tests.

This directory has its own dependencies and tests; it does not import backend code or sibling examples.

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```
