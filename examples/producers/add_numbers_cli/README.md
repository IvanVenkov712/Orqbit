# Add numbers CLI producer

A standalone producer that submits an `add_numbers` job through Orqbit's public HTTP API. It accepts one or more finite JSON numbers, prints the job ID, and optionally waits for the result. The worker performs the addition independently.

## Setup

Start Orqbit with its current database migrations applied and authenticate using the [quickstart](../../../docs/quickstart.md). Register a producer with your **user bearer token** using `POST /producers`:

```json
{"name":"add-numbers-cli"}
```

Save the returned `secret_api_key`. From this directory, with Python 3.13 and uv installed:

```powershell
uv sync
Copy-Item .env.example .env
```

If `.env` already exists, edit it instead of overwriting it. Set `API_KEY` to the **producer** key and `API_URL` to the API address. The adjacent `.env` is loaded regardless of working directory; environment variables override file values. Keep the real `.env` private.

| Setting | Default | Meaning |
| --- | --- | --- |
| `API_KEY` | Required | Registered producer's secret API key |
| `API_URL` | Required | API base URL, for example `http://127.0.0.1:8000` |
| `POLL_INTERVAL` | 2 | Seconds between status polls when waiting |
| `REQUEST_TIMEOUT` | 10 | HTTP timeout in seconds |

Timing settings must be positive and finite. Start the [add_numbers worker](../../workers/add_numbers/README.md), registered under the **same user** as the producer: this example submits jobs with `permission_policy: PRIVATE`.

## Run

Submit and return immediately:

```powershell
uv run python producer.py 2 3 5
```

Output:

```text
Idempotency-Key: <generated UUID>
job_id: 42
```

The key is written to stderr before the POST; the ID is written to stdout once the API responds. Successful submission does not mean execution has succeeded.

Wait for completion, allowing up to 30 seconds after submission:

```powershell
uv run python producer.py --wait --wait-timeout 30 2 3 5
```

On success, the job ID is followed by:

```text
status: SUCCEEDED
result: {"sum": 10}
```

`--wait-timeout` defaults to 60 seconds and applies only with `--wait`. Polling stops at `SUCCEEDED`, `FAILED`, an API error, or expiration of the local waiting period. Each polling request's timeout is capped by the remaining waiting period. A failed job prints its stored `error`. Stopping the CLI or reaching a timeout does not cancel the job.

Integers, decimals, and exponent notation are supported. Strings, booleans, NaN, infinity, and missing numbers are rejected before an API request. For negative exponent arguments that argparse could mistake for options, put options before `--`, then the numbers:

```powershell
uv run python producer.py --wait -- -2e3 3.5 5
```

Exit codes: `0` for accepted submission without waiting or a successful terminal job with waiting; `1` for configuration/API errors, a failed job, or an expired wait; `2` for invalid CLI arguments; `130` for Ctrl+C.

## Request flow and safe repetition

1. Validate the command-line numbers.
2. Prepare the following payload:
   ```json
   {
     "job_type": "add_numbers",
     "params": {"numbers": [2, 3, 5]},
     "permission_policy": "PRIVATE"
   }
   ```
3. Generate a UUID idempotency key unless `--idempotency-key` was supplied.
4. Send `POST /producer/jobs` with `X-API-Key` and `Idempotency-Key` headers.
5. Print the returned job ID.
6. With `--wait`, read `GET /producer/jobs/{job_id}` until a terminal outcome or the local waiting period expires. An already terminal submission replay is used immediately.

A timeout or lost response can occur **after the server has stored the job**. There are no automatic HTTP retries. To repeat a submission, use the same producer credentials, numbers in the same order, and original key:

```powershell
uv run python producer.py --idempotency-key addition-example-001 2 3 5
uv run python producer.py --idempotency-key addition-example-001 --wait 2 3 5
```

A matching replay returns the existing job. Changing the numbers with the same key returns HTTP 409. Omitting `--idempotency-key` generates a fresh key on each invocation and creates a separate job. The CLI accepts keys of 1-100 printable ASCII characters, with at least one non-space character. The server currently scopes keys by the owning user, so that user's other producers and direct submissions share the namespace; generated UUIDs help avoid accidental collisions. Keep the key if you need to repeat after a restart; this CLI does not persist submissions locally.

HTTP errors print their status without response bodies or credentials. Check the producer key for 401, input/access policy for 422, and idempotency-key reuse for 409. HTTP 503 can also leave the submission outcome uncertain; use the original key when repeating.

## Code and tests

- `producer.py`: CLI validation, idempotency key generation, submission flow, and optional polling.
- `api.py`: authenticated submission and status requests using the Python standard library.
- `settings.py`: validated configuration, following the existing worker examples.
- `tests/test_producer.py`: focused configuration, HTTP, CLI, and polling tests with mocked HTTP and time.

This directory has its own dependencies and tests and can be copied and run without backend or worker imports.

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```
