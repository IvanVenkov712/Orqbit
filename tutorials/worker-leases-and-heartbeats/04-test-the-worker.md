# 4. Test without real delays

[← Execute and report](03-execute-and-report.md) · [Tutorial home](README.md) · [Next: Run and observe →](05-run-and-observe.md)

Use the existing example's tests as a starting point. They simulate time and HTTP responses, so a long execution finishes immediately in the test suite. No live server or database is needed.

## Copy and adapt the existing tests

From your **`examples/workers/delayed_greeting/`** directory:

```powershell
New-Item -ItemType Directory -Path tests
Copy-Item ../delay_with_heartbeat/tests/*.py -Destination tests
```

On macOS or Linux:

```sh
mkdir tests
cp ../delay_with_heartbeat/tests/*.py tests/
```

Make these small edits:

1. In `tests/conftest.py`, change the `attempt` fixture's `job_type` from `delay_with_heartbeat` to `delayed_greeting`, and its `params` from `{}` to `{"name": "Taylor"}`.
2. In `tests/test_worker.py`, inside `test_long_task_finishes_after_renewed_initial_lease`, replace the expected success payload with:

   ```python
   assert payload == {
       "result": {"greeting": "Hello, Taylor!", "waited_seconds": 12}
   }
   ```

The fixture uses a 12-second task and an initial 10-second lease. Its virtual clock advances whenever the worker sleeps; mocked heartbeats renew the deadline. The test verifies success **after the original deadline**, with renewals occurring before each current deadline.

## Add focused input validation coverage

Create **`tests/test_execution.py`**:

```python
from unittest.mock import Mock

import pytest

import execution


@pytest.mark.parametrize("params", [{}, {"name": " "}, {"name": 42}])
def test_invalid_name_does_not_start_work(
    monkeypatch, settings, attempt, clock, params
):
    attempt["params"] = params
    wait = Mock()
    post = Mock()
    monkeypatch.setattr(execution, "wait_with_heartbeats", wait)
    monkeypatch.setattr(execution, "post", post)

    execution.process_attempt(settings, attempt)

    wait.assert_not_called()
    post.assert_called_once_with(
        settings,
        "workers/17/fail",
        {
            "error": {
                "code": "INVALID_PARAMS",
                "message": "name must be non-empty text",
            }
        },
    )
```

## Run the checks

From the same worker directory:

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

If Ruff requests formatting, run `uv run --locked ruff format .` in **your new worker directory**, then repeat the checks.

The inherited tests cover malformed deadlines, an already-expired claim, oversleeping beyond expiry, zero-duration work, heartbeat rejection, lost connections, empty queues, settings, and HTTP authentication. They also verify that heartbeat failure stops the worker without an outcome report. The new tests verify your greeting input rules.

These are worker-side tests with mocked HTTP. They do not prove database locking or server recovery behavior; the backend has its own integration tests for those responsibilities.

[Continue to step 5 →](05-run-and-observe.md)
