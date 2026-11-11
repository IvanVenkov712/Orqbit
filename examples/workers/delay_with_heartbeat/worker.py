"""Standalone delay_with_heartbeat worker."""

import logging
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError

from pydantic import ValidationError

from api import claim, post
from settings import Settings

logger = logging.getLogger(__name__)


class LeaseLost(Exception):
    """The attempt is no longer safe to execute or report."""


def wait_with_heartbeats(settings: Settings, attempt: dict) -> None:
    """Wait in short steps, renewing ownership before the lease expires."""
    attempt_id = attempt["id"]
    message = (
        f"Ownership of attempt {attempt_id} could not be confirmed; "
        "execution stopped without reporting an outcome"
    )
    try:
        deadline = datetime.fromisoformat(attempt["lease_expires_at"])
        finish_at = time.monotonic() + settings.execution_delay
        while True:
            remaining_lease = (deadline - datetime.now(UTC)).total_seconds()
            if remaining_lease <= 0:
                raise LeaseLost(message)
            remaining_work = finish_at - time.monotonic()
            if remaining_work <= 0:
                return

            time.sleep(
                min(
                    remaining_work,
                    settings.heartbeat_interval,
                    remaining_lease / 3,
                )
            )
            if datetime.now(UTC) >= deadline:
                raise LeaseLost(message)
            if time.monotonic() >= finish_at:
                return

            renewed = post(settings, f"workers/{attempt_id}/heartbeat")
            deadline = datetime.fromisoformat(renewed["lease_expires_at"])
            logger.info("Renewed lease for attempt %s until %s", attempt_id, deadline)
    except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError):
        raise LeaseLost(message) from None


def run_once(settings: Settings) -> bool:
    """Claim and report one attempt; return False when the queue is empty."""
    attempt = claim(settings)
    if attempt is None:
        return False

    if attempt["job_type"] != "delay_with_heartbeat":
        post(
            settings,
            f"workers/{attempt['id']}/fail",
            {
                "error": {
                    "code": "UNSUPPORTED_JOB_TYPE",
                    "message": "This worker only supports delay_with_heartbeat",
                }
            },
        )
    else:
        wait_with_heartbeats(settings, attempt)
        post(
            settings,
            f"workers/{attempt['id']}/succeed",
            {
                "result": {"waited_seconds": settings.execution_delay},
            },
        )

    logger.info("Reported outcome for attempt %s", attempt["id"])
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        settings = Settings()
        logger.info("delay_with_heartbeat worker started; press Ctrl+C to stop")
        while True:
            if not run_once(settings):
                time.sleep(settings.poll_interval)
    except KeyboardInterrupt:
        logger.info("Worker stopped")
        return 0
    except ValidationError:
        logger.error("Invalid worker configuration; check the worker's .env")
    except LeaseLost as exc:
        logger.error("%s", exc)
    except HTTPError as exc:
        logger.error("API request failed with HTTP %s; worker stopped", exc.code)
    except (URLError, OSError, TimeoutError):
        logger.error("API connection failed; worker stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
