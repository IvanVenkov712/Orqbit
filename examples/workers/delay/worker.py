"""Standalone delay worker."""

import logging
import time
from urllib.error import HTTPError, URLError

from pydantic import ValidationError

from api import claim, post
from settings import Settings

logger = logging.getLogger(__name__)


def run_once(settings: Settings) -> bool:
    """Claim and report one attempt; return False when the queue is empty."""
    attempt = claim(settings)
    if attempt is None:
        return False

    if attempt["job_type"] != "delay":
        post(
            settings,
            f"workers/{attempt['id']}/fail",
            {
                "error": {
                    "code": "UNSUPPORTED_JOB_TYPE",
                    "message": "This worker only supports delay",
                }
            },
        )
    else:
        time.sleep(settings.execution_delay)
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
        logger.info("delay worker started; press Ctrl+C to stop")
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
