# Build an independent producer

[All tutorials](../README.md) · [Getting started with Orqbit](../getting-started/README.md)

Build a Python CLI that submits an `add_numbers` job, prints its ID, and optionally waits for the worker's result. You will use the [recommended producer structure](../../docs/architecture.md#recommended-producer-architecture), with a small HTTP module, validated configuration, one entry point, and local tests. The finished program follows the supplied [CLI producer](../../examples/producers/add_numbers_cli/README.md).

You need basic Python, a checkout of this repository, Python 3.13, and uv. See [installation](../getting-started/01-install-and-open.md) and [Python/uv setup](../getting-started/04-start-your-worker.md#install-uv-and-python) if needed. Commands use PowerShell; macOS/Linux alternatives are included where they differ. Put code listings in the named files using your editor.

The tests below need no server. For the final live run, you need Orqbit running, a [registered producer](../getting-started/09-register-a-producer.md), and an [addition worker](../getting-started/04-start-your-worker.md) owned by the same user. Use the producer key for this application and the worker key for the worker.

## 1. Prepare an independent application

Your finished directory will look like this:

```text
my_producer/
  pyproject.toml       Own dependencies and test/lint configuration
  uv.lock              Locked dependency versions
  .env.example         Configuration placeholders
  .env                 Private local configuration, excluded from Git
  settings.py          Validated configuration
  api.py               Public producer HTTP requests
  producer.py          CLI input, submission key, submission, and polling
  tests/
    test_producer.py   Mocked HTTP, input, polling, and shutdown tests
```

Start at the **repository root**. Reuse the example's dependency files and configuration template so your application has the same tested setup:

```powershell
New-Item -ItemType Directory -Path examples/producers/my_producer
Copy-Item examples/producers/add_numbers_cli/pyproject.toml examples/producers/my_producer/
Copy-Item examples/producers/add_numbers_cli/uv.lock examples/producers/my_producer/
Copy-Item examples/producers/add_numbers_cli/.env.example examples/producers/my_producer/
cd examples/producers/my_producer
uv sync --locked
```

On macOS/Linux:

```sh
mkdir -p examples/producers/my_producer
cp examples/producers/add_numbers_cli/pyproject.toml examples/producers/my_producer/
cp examples/producers/add_numbers_cli/uv.lock examples/producers/my_producer/
cp examples/producers/add_numbers_cli/.env.example examples/producers/my_producer/
cd examples/producers/my_producer
uv sync --locked
```

The copied project metadata retains the reference project's name; its files and environment are now local to your directory. `pyproject.toml` declares Pydantic and pydantic-settings, plus pytest and Ruff for development. HTTP uses Python's standard library. uv creates this application's own `.venv`; it does not use the backend's environment.

All subsequent commands run **inside `examples/producers/my_producer/`**. No backend imports, database connection, or worker business logic belong in this application.

## 2. Load and validate configuration

Create `settings.py`:

```python
"""Producer configuration read from the adjacent .env file."""

from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().with_name(".env"),
        extra="ignore",
        hide_input_in_errors=True,
    )

    api_key: SecretStr = Field(min_length=1)
    api_url: AnyHttpUrl
    poll_interval: float = Field(default=2, gt=0, allow_inf_nan=False)
    request_timeout: float = Field(default=10, gt=0, allow_inf_nan=False)
```

`API_KEY` and `API_URL` are required. Timing values must be positive and finite. The file path is relative to `settings.py`, so launching from another directory still loads the correct `.env`. Terminal environment variables take precedence over that file. `SecretStr` masks the key in ordinary representations; the HTTP code will explicitly unwrap it for authentication.

You can leave the real `.env` until the live run. The tests provide their own configuration without reading credentials.

## 3. Keep HTTP requests in a small module

Create `api.py`:

```python
"""HTTP requests to Orqbit's public producer API."""

import json
from urllib.request import Request, urlopen

from settings import Settings


def submit_job(
    settings: Settings, numbers: list[int | float], idempotency_key: str
) -> dict:
    payload = {
        "job_type": "add_numbers",
        "params": {"numbers": numbers},
        "permission_policy": "PRIVATE",
    }
    request = Request(
        f"{str(settings.api_url).rstrip('/')}/producer/jobs",
        data=json.dumps(payload, allow_nan=False).encode(),
        headers={
            "X-API-Key": settings.api_key.get_secret_value(),
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=settings.request_timeout) as response:
        return json.load(response)


def get_job(settings: Settings, job_id: int, *, timeout: float) -> dict:
    request = Request(
        f"{str(settings.api_url).rstrip('/')}/producer/jobs/{job_id}",
        headers={"X-API-Key": settings.api_key.get_secret_value()},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)
```

These are the dedicated **producer** routes, authenticated with `X-API-Key`. The plural `/producers` route registers applications using a user bearer token; it is a different operation. Producers can read only jobs submitted by their own registration, including when another producer belongs to the same user.

The payload matches the existing worker's input contract: `add_numbers` and `{"numbers":[2,3,5]}`. `PRIVATE` allows a compatible worker belonging to the producer's owner to claim the job. The API stores the request; the worker performs the addition.

Every POST also sends an `Idempotency-Key`. One intended operation gets one key and one exact payload. Repeating that combination through the same producer returns the existing job. Changed content or a key reserved by another producer/direct user submission returns 409. The namespace is the owning user, so generated UUIDs avoid accidental collisions across that user's applications. See the [producer API contract](../../docs/api.md#producer-jobs).

## 4. Implement input, submission, and optional polling

Create `producer.py` with this complete entry point:

```python
"""Submit an add_numbers job and optionally wait for its outcome."""

import argparse
import json
import math
import sys
import time
from urllib.error import HTTPError, URLError
from uuid import uuid4

from pydantic import ValidationError

from api import get_job, submit_job
from settings import Settings


def number(value: str) -> int | float:
    try:
        parsed = json.loads(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a finite number") from None
    if type(parsed) not in (int, float) or (
        isinstance(parsed, float) and not math.isfinite(parsed)
    ):
        raise argparse.ArgumentTypeError("expected a finite number")
    return parsed


def positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected positive finite seconds") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("expected positive finite seconds")
    return seconds


def submission_key(value: str) -> str:
    if (
        not 1 <= len(value) <= 100
        or not value.strip()
        or any(ord(char) < 32 or ord(char) > 126 for char in value)
    ):
        raise argparse.ArgumentTypeError(
            "expected 1-100 printable ASCII characters, not only spaces"
        )
    return value


def wait_for_job(settings: Settings, job: dict, timeout: float) -> dict | None:
    """Poll until terminal; return None if the local waiting period expires."""
    deadline = time.monotonic() + timeout
    while job["status"] not in ("SUCCEEDED", "FAILED"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        job = get_job(
            settings, job["id"], timeout=min(settings.request_timeout, remaining)
        )
        if job["status"] not in ("SUCCEEDED", "FAILED"):
            time.sleep(min(settings.poll_interval, max(0, deadline - time.monotonic())))
    return job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numbers", nargs="+", type=number, help="finite JSON numbers")
    parser.add_argument(
        "--idempotency-key",
        type=submission_key,
        help="reuse for an identical submission",
    )
    parser.add_argument("--wait", action="store_true", help="wait for the job outcome")
    parser.add_argument(
        "--wait-timeout",
        type=positive_seconds,
        default=60,
        help="maximum local waiting period in seconds (default: 60)",
    )
    args = parser.parse_args(argv)

    try:
        settings = Settings()
        key = args.idempotency_key or str(uuid4())
        print(f"Idempotency-Key: {key}", file=sys.stderr, flush=True)
        job = submit_job(settings, args.numbers, key)
        print(f"job_id: {job['id']}", flush=True)
        if not args.wait:
            return 0
        job = wait_for_job(settings, job, args.wait_timeout)
        if job is None:
            print("Waiting period expired; the job was not cancelled.", file=sys.stderr)
            return 1
        print(f"status: {job['status']}")
        field = "result" if job["status"] == "SUCCEEDED" else "error"
        print(f"{field}: {json.dumps(job[field], ensure_ascii=True)}")
        return 0 if job["status"] == "SUCCEEDED" else 1
    except ValidationError:
        print(
            "Invalid producer configuration; check the producer's .env.",
            file=sys.stderr,
        )
    except HTTPError as exc:
        print(f"API request failed with HTTP {exc.code}.", file=sys.stderr)
    except (URLError, OSError, TimeoutError):
        print(
            "API connection failed. If submission was attempted, repeat with the same "
            "--idempotency-key and numbers.",
            file=sys.stderr,
        )
    except (ValueError, KeyError, TypeError):
        print("Invalid API response.", file=sys.stderr)
    except KeyboardInterrupt:
        print("Producer stopped; submitted jobs are not cancelled.", file=sys.stderr)
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

The flow is deliberately sequential:

1. **Validate input before HTTP.** `json.loads()` preserves integers and accepts decimals/exponents. The explicit type check rejects booleans, which Python otherwise treats as integers. NaN, infinity, strings, and missing numbers are rejected. Explicit keys are limited to 1–100 printable ASCII characters with a non-space character.
2. **Prepare one operation key.** Accept `--idempotency-key` or generate a UUID. Print it to stderr before the POST, so it remains available if the response is lost. This identifier is separate from the secret API key.
3. **Submit once and print the ID.** Without `--wait`, accepted submission ends the command. Execution can still be Pending or Running.
4. **Poll only when requested.** `SUCCEEDED` and `FAILED` stop polling, including if a replay already returned a terminal job. A monotonic deadline bounds the local waiting period; each read timeout and sleep is capped by the remaining time. Submission has its separate request timeout and happens before the waiting period begins.
5. **Report outcomes without cancelling work.** Success prints `result`; failure prints the stored structured `error`. Timeout, Ctrl+C, and HTTP failures end this process without cancelling accepted jobs.

There are no automatic HTTP retries. A timeout, connection failure, or temporary server error such as 503 can leave submission uncertain: the server may have stored the job before its response was lost. Retain the original key and payload, then repeat explicitly through the same producer. A new key means new work. Error diagnostics omit raw HTTP response bodies and credentials.

Exit codes are `0` for accepted submission without waiting or a successful result, `1` for failure/configuration/transport/wait errors, `2` for invalid CLI arguments, and `130` for Ctrl+C. A polling request can fail before the overall deadline; this example stops on that error rather than silently retrying it.

## 5. Reuse and run the focused tests

The implementation matches the supplied CLI's public functions, so reuse its existing tests. Still inside your new producer directory:

```powershell
New-Item -ItemType Directory -Path tests
Copy-Item ../add_numbers_cli/tests/test_producer.py tests/test_producer.py
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

On macOS/Linux, the first two commands are:

```sh
mkdir -p tests
cp ../add_numbers_cli/tests/test_producer.py tests/test_producer.py
```

Then run the same three `uv run --locked` checks. The tests now live inside your application and import only its own modules. You can copy this directory elsewhere without keeping the original example or backend alongside it.

Read `tests/test_producer.py` as you run it:

| Behavior | What the tests establish |
| --- | --- |
| Submission/read requests | Correct producer routes, authentication, key, payload, and timeouts. |
| Input validation | Invalid numbers, keys, and waiting limits fail before submission. |
| Submission identity | Generated keys are printed before sending; an explicit key survives repeated invocations. |
| Lost responses | Timeout/connection errors do not trigger automatic resubmission or expose credentials. |
| Polling | Pending/Running lead to Success or Failure; controlled time bounds waiting without real sleeps or another POST. |
| Shutdown and configuration | Ctrl+C leaves accepted jobs alone; adjacent `.env` loading, environment precedence, and secret-safe errors work. |

HTTP and time are mocked. These tests validate the producer's behavior; server-side deduplication, ownership, and PostgreSQL concurrency remain the backend integration tests' responsibility.

## 6. Register, configure, and run against Orqbit

Follow [Register a producer](../getting-started/09-register-a-producer.md) and save its key. Start an `add_numbers` worker registered under the **same account** in another terminal. Keep both the API and worker running.

Inside **your new directory**, create `.env` once:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux use `cp .env.example .env`. Edit an existing `.env` instead of overwriting it. Set:

```dotenv
API_KEY=PASTE_YOUR_PRODUCER_KEY_HERE
API_URL=http://127.0.0.1:8000
POLL_INTERVAL=2
REQUEST_TIMEOUT=10
```

Use your installation's API base URL if different. The local browser interface is on port 8080; this producer calls the API on **8000**. Keep `.env` private; the repository's `.gitignore` already excludes it. If copying the application to another repository, exclude `.env` and `.venv` there too, while keeping `.env.example` and `uv.lock`.

Run:

```powershell
uv run --locked python producer.py --wait --wait-timeout 30 2 3 5
```

Expected output, with your own key and job ID:

```text
Idempotency-Key: <generated UUID>
job_id: 42
status: SUCCEEDED
result: {"sum": 10}
```

Open the printed job ID under **Jobs** in the browser, signed in as the producer's owner. It should show the same result and the worker's execution attempt. This completes the real path: **producer → HTTP API → stored job → worker → stored result → producer**.

Try explicit repetition with a key unused by your account:

```powershell
uv run --locked python producer.py --idempotency-key my-producer-demo-001 2 3 5
uv run --locked python producer.py --idempotency-key my-producer-demo-001 --wait 2 3 5
```

Both runs should print the same job ID. Changing `5` to `6` with that same key should return HTTP 409. Invalid input such as `true` should fail locally without an API request:

```powershell
uv run --locked python producer.py true
```

If a job stays Pending, check the worker's type, credentials, process, and ownership. If no result arrives within 30 seconds, inspect the job in the browser; the waiting limit does not cancel it. For configuration, connection, and status errors, use the [producer troubleshooting table](../getting-started/10-start-your-producer.md#common-problems).

## 7. Adapt the producer to your own workload

Keep the same structure. Change CLI input/validation in `producer.py`, then change the `job_type` and `params` construction in `api.py` to match your worker's documented contract. Update tests for the new payload, invalid inputs, and result. Only add another domain module if that logic becomes substantial; registration does not install worker code or define a server-side parameter schema.

This CLI has no durable local record of keys or job IDs. Save them yourself when needed. Stopping it loses local tracking while accepted jobs remain on the server. Submission deduplication also does not guarantee that a retried worker's external effects happen exactly once.

For continuous console input, see the [console producer](../../examples/producers/add_numbers_console/README.md), which uses a queue and a background loop with an explicit retry policy. Durable restart recovery and coordinating submission with your own application's database need separate requirements; they are outside this walkthrough.

[Back to all tutorials](../README.md) · [Producer API reference](../../docs/api.md#producer-jobs)
