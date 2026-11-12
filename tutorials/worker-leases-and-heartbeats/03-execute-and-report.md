# 3. Execute work and report outcomes

[← Implement heartbeats](02-implement-heartbeats.md) · [Tutorial home](README.md) · [Next: Test the worker →](04-test-the-worker.md)

Our job type is **`delayed_greeting`**. It accepts a Text parameter named `name`. The waiting time comes from the worker's settings, not the job's parameters.

Create **`execution.py`** in your new worker directory:

```python
"""Validate and execute one delayed_greeting attempt."""

from api import post
from heartbeat import (
    read_deadline,
    remaining_lease_seconds,
    wait_with_heartbeats,
)
from settings import Settings


def process_attempt(settings: Settings, attempt: dict) -> None:
    attempt_id = attempt["id"]
    remaining_lease_seconds(read_deadline(attempt, attempt_id), attempt_id)

    if attempt["job_type"] != "delayed_greeting":
        outcome = "fail"
        payload = {
            "error": {
                "code": "UNSUPPORTED_JOB_TYPE",
                "message": "This worker only supports delayed_greeting",
            }
        }
    else:
        name = attempt["params"].get("name")
        if not isinstance(name, str) or not name.strip():
            outcome = "fail"
            payload = {
                "error": {
                    "code": "INVALID_PARAMS",
                    "message": "name must be non-empty text",
                }
            }
        else:
            wait_with_heartbeats(settings, attempt)
            outcome = "succeed"
            payload = {
                "result": {
                    "greeting": f"Hello, {name.strip()}!",
                    "waited_seconds": settings.execution_delay,
                }
            }

    post(settings, f"workers/{attempt_id}/{outcome}", payload)
```

The copied `worker.py` already imports this function. It handles claiming and calls it once for each returned attempt. No changes to the backend are required.

## Keep task errors and lease loss separate

| Situation | Worker behavior |
| --- | --- |
| Valid name and a completed wait | Send `{"result": {...}}` to `/workers/{attempt_id}/succeed`. |
| Missing or blank name, or a non-text value | Send a structured `INVALID_PARAMS` error to `/workers/{attempt_id}/fail`, while the lease is valid. |
| Unsupported job type | Report `UNSUPPORTED_JOB_TYPE`; register this worker only for the type it implements. |
| Expired lease, rejected heartbeat, or uncertain connection during renewal | Let `LeaseLost` propagate to the main loop. Stop without reporting an outcome. |
| Outcome request fails | Stop and inspect the saved job state. Do not automatically send a contradictory failure report. |

Use **`attempt["id"]`**, not `attempt["job_id"]`, in heartbeat and outcome URLs. A job can have several attempts; each attempt has its own identity, ownership, and deadline.

The server checks ownership, allowed transitions, and expiry again when it accepts an outcome. Worker-reported failure is terminal, even if automatic retries are configured for lost attempts. An exact replay of an accepted outcome is supported by the API, but this example deliberately has no HTTP retry loop.

[Continue to step 4 →](04-test-the-worker.md)
