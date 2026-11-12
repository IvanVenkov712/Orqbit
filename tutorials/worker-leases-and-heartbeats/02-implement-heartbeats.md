# 2. Implement lease renewal

[← Create the worker](01-create-the-worker.md) · [Tutorial home](README.md) · [Next: Execute and report →](03-execute-and-report.md)

Create **`heartbeat.py`** in your new worker directory. Use this implementation, matching the supplied `delay_with_heartbeat` example:

```python
"""Wait while keeping the claimed attempt's lease valid."""

import logging
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError

from api import post
from settings import Settings

logger = logging.getLogger(__name__)


class LeaseLost(Exception):
    """The attempt is no longer safe to execute or report."""

    def __init__(self, attempt_id: int) -> None:
        super().__init__(
            f"Ownership of attempt {attempt_id} could not be confirmed; "
            "execution stopped without reporting an outcome"
        )


def read_deadline(response: dict, attempt_id: int) -> datetime:
    """Read the timezone-aware deadline from a claim or heartbeat response."""
    try:
        deadline = datetime.fromisoformat(response["lease_expires_at"])
    except (ValueError, KeyError, TypeError):
        raise LeaseLost(attempt_id) from None
    if deadline.tzinfo is None:
        raise LeaseLost(attempt_id)
    return deadline


def remaining_lease_seconds(deadline: datetime, attempt_id: int) -> float:
    """Return the remaining lease, stopping execution when it has expired."""
    remaining = (deadline - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        raise LeaseLost(attempt_id)
    return remaining


def renew_lease(settings: Settings, attempt_id: int) -> datetime:
    """Send one heartbeat and return the server's new deadline."""
    try:
        response = post(settings, f"workers/{attempt_id}/heartbeat")
    except (HTTPError, URLError, OSError):
        raise LeaseLost(attempt_id) from None

    deadline = read_deadline(response, attempt_id)
    logger.info("Renewed lease for attempt %s until %s", attempt_id, deadline)
    return deadline


def wait_with_heartbeats(settings: Settings, attempt: dict) -> None:
    """Wait in short steps and renew the lease while work remains."""
    attempt_id = attempt["id"]
    deadline = read_deadline(attempt, attempt_id)
    finish_at = time.monotonic() + settings.execution_delay

    while True:
        remaining_lease = remaining_lease_seconds(deadline, attempt_id)
        remaining_work = finish_at - time.monotonic()
        if remaining_work <= 0:
            return

        sleep_seconds = min(
            remaining_work,
            settings.heartbeat_interval,
            remaining_lease / 3,
        )
        time.sleep(sleep_seconds)
        remaining_lease_seconds(deadline, attempt_id)

        if time.monotonic() < finish_at:
            deadline = renew_lease(settings, attempt_id)
```

## Why these checks matter

1. **Read the server deadline.** Claims and heartbeats return `lease_expires_at`. Missing, invalid, or timezone-free deadlines stop the attempt.
2. **Check before and after a work step.** A process can be delayed by the operating system. If it wakes after expiry, it stops instead of trying to revive the lease.
3. **Leave time to renew.** Each wait is capped at the heartbeat interval and one third of the remaining lease. This leaves headroom for the request. It is a practical margin, not a guarantee under arbitrary network delays.
4. **Replace the deadline after a heartbeat.** `POST /workers/{attempt_id}/heartbeat` has no request body. The API key identifies the worker; the path identifies its attempt. The returned deadline is used on the next loop.
5. **Stop on uncertainty.** A failed request or unusable renewal raises `LeaseLost`. The main loop exits without sending success or failure for that attempt.

Lease comparisons use UTC wall-clock time because the server sends a timestamp. Task duration uses `time.monotonic()` so local clock adjustments do not change the planned wait. Keep the worker machine's clock synchronized with the server; local checks supplement the server's checks.

The final loop iteration checks expiry before returning. There is still a gap between that check and the outcome request: if the request arrives late, the server rejects it. Do not turn that rejection into a second outcome report.

[Continue to step 3 →](03-execute-and-report.md)
