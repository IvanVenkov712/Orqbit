"""Polling loop and command-line entry point for the delay_with_heartbeat worker."""

import logging
import time
from urllib.error import HTTPError, URLError

from pydantic import ValidationError

from api import claim
from execution import process_attempt
from heartbeat import LeaseLost
from settings import Settings

logger = logging.getLogger(__name__)


def run_once(settings: Settings) -> bool:
    """Claim and process one attempt; return False when the queue is empty."""
    attempt = claim(settings)
    if attempt is None:
        return False

    process_attempt(settings, attempt)
    logger.info("Reported outcome for attempt %s", attempt["id"])
    return True


def run_forever(settings: Settings) -> None:
    """Process available jobs and pause only when the queue is empty."""
    while True:
        if not run_once(settings):
            time.sleep(settings.poll_interval)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        settings = Settings()
        logger.info("delay_with_heartbeat worker started; press Ctrl+C to stop")
        run_forever(settings)
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
