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
