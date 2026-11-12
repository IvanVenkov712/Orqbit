# 7. Create your own worker (optional)

[← Progress and results](06-progress-and-results.md) · [Tutorial home](README.md) · [Next: Everyday use and troubleshooting →](08-everyday-use-and-troubleshooting.md)

**Goal:** create a small worker that takes a name and returns a greeting.

This step involves editing Python. If you just want to use the supplied workers, you can [skip ahead](08-everyday-use-and-troubleshooting.md).

For a complete worker that renews its lease during longer tasks, follow the separate [leases and heartbeats tutorial](../worker-leases-and-heartbeats/README.md).

You will reuse the addition example's connection and configuration files. Your new worker will have its own folder, dependencies, key, and execution logic. No server changes are needed.

## Prepare a separate folder

Open a **new terminal at the repository root**. Keep any existing worker in its own terminal.

In PowerShell:

```powershell
New-Item -ItemType Directory -Path examples/workers/greet_user
Copy-Item -Path examples/workers/add_numbers/api.py, examples/workers/add_numbers/settings.py, examples/workers/add_numbers/pyproject.toml, examples/workers/add_numbers/.env.example -Destination examples/workers/greet_user
cd examples/workers/greet_user
```

On macOS or Linux:

```sh
mkdir examples/workers/greet_user
cp examples/workers/add_numbers/api.py examples/workers/add_numbers/settings.py examples/workers/add_numbers/pyproject.toml examples/workers/add_numbers/.env.example examples/workers/greet_user/
cd examples/workers/greet_user
```

This copies the reusable source and dependency list. Your addition worker's private configuration and environment stay in its original folder.

Open the copied `pyproject.toml` and change just the project name:

```toml
name = "orqbit-greet-user-worker"
```

Keep the other contents, then run:

```powershell
uv sync
```

The first sync creates this worker's own `.venv` and `uv.lock`. On subsequent runs you can use `uv sync --locked`, as with the supplied examples.

## Write the worker

Create **`worker.py`** inside `examples/workers/greet_user/` and paste the complete code below. Make sure your editor saves it as `worker.py`, rather than `worker.py.txt`.

```python
"""A standalone worker for the greet_user job type."""

import logging
import time
from urllib.error import HTTPError, URLError

from pydantic import ValidationError

from api import claim, post
from settings import Settings

logger = logging.getLogger(__name__)


def greet_user(params: dict) -> dict:
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be non-empty text")
    return {"greeting": f"Hello, {name.strip()}!"}


def run_once(settings: Settings) -> bool:
    attempt = claim(settings)
    if attempt is None:
        return False

    if attempt["job_type"] != "greet_user":
        outcome = "fail"
        payload = {
            "error": {
                "code": "UNSUPPORTED_JOB_TYPE",
                "message": "This worker only supports greet_user",
            }
        }
    else:
        try:
            result = greet_user(attempt["params"])
        except ValueError as exc:
            outcome = "fail"
            payload = {"error": {"code": "INVALID_PARAMS", "message": str(exc)}}
        else:
            outcome = "succeed"
            payload = {"result": result}

    post(settings, f"workers/{attempt['id']}/{outcome}", payload)
    logger.info("Reported outcome for attempt %s", attempt["id"])
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        settings = Settings()
        logger.info("greet_user worker started; press Ctrl+C to stop")
        while True:
            if not run_once(settings):
                time.sleep(settings.poll_interval)
    except KeyboardInterrupt:
        logger.info("Worker stopped")
        return 0
    except ValidationError:
        logger.error("Invalid worker configuration; check the worker's .env")
    except HTTPError as exc:
        logger.error("API request failed with HTTP %s; worker stopped", exc.code)
    except (URLError, OSError, TimeoutError):
        logger.error("API connection failed; worker stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

`greet_user` is the part that does your work. The remaining code asks for a job, reports either a result or an input error, and waits when the queue is empty. It uses the **attempt ID** returned by the claim when reporting an outcome.

This example is for quick work that finishes inside the default 120-second execution window, including the time needed to report the result. For longer tasks, start from [`delay_with_heartbeat`](../../examples/workers/delay_with_heartbeat/README.md) or [`count_primes`](../../examples/workers/count_primes/README.md), which renew that window while working.

## Check the greeting before connecting

Create a `tests` folder in `greet_user`, then create **`tests/test_worker.py`**:

```python
import pytest

from worker import greet_user


def test_greeting():
    assert greet_user({"name": " Taylor "}) == {"greeting": "Hello, Taylor!"}


@pytest.mark.parametrize("params", [{}, {"name": " "}, {"name": 42}])
def test_invalid_name(params):
    with pytest.raises(ValueError, match="name must be non-empty text"):
        greet_user(params)
```

From `examples/workers/greet_user/`, run:

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The tests should report **4 passed**. These checks do not need a running Orqbit server.

## Register and start your new worker

In the browser, follow [step 3](03-register-a-worker.md) again with:

| Field | Value |
| --- | --- |
| Worker name | `my-greeter`, or another unused name. |
| Supported types | `greet_user` |
| Visibility policy | **Private** |

Save the **new** API key. Back in the `greet_user` terminal, create its configuration:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux, use `cp .env.example .env`.

Edit `.env`: set `API_KEY` to the greeter's key and `API_URL` to `http://127.0.0.1:8000` for the local tutorial setup. Save it, then run:

```powershell
uv run --locked python worker.py
```

Leave the terminal running.

## Send it a job

In **Jobs → Submit a job**:

1. Enter job type `greet_user`.
2. Add a parameter named `name`, choose **Text**, and enter `Taylor`.
3. Keep **Private** access and select **Submit job**.

The job should Succeed with:

```json
{
  "greeting": "Hello, Taylor!"
}
```

For your next worker, define the inputs and result first, then adapt the work function, supported type, and tests together. Keep everything it needs in its own directory; workers communicate with Orqbit through its HTTP API.

These small examples stop on connection errors and do not automatically retry HTTP requests. If a result response is lost, check the saved job status before submitting the work again.

[Continue to 8. Everyday use and troubleshooting →](08-everyday-use-and-troubleshooting.md)
