"""Standalone add_numbers worker."""

import logging
import math
import time
from urllib.error import HTTPError, URLError

from pydantic import ValidationError

from api import claim, post
from settings import Settings

logger = logging.getLogger(__name__)


def add_numbers(params: dict) -> dict:
    numbers = params.get("numbers")
    if not isinstance(numbers, list) or any(
        type(number) not in (int, float)
        or (isinstance(number, float) and not math.isfinite(number))
        for number in numbers
    ):
        raise ValueError("numbers must be a list of finite numbers")

    try:
        total = sum(numbers)
    except OverflowError:
        raise ValueError("sum is outside the supported numeric range") from None
    if isinstance(total, float) and not math.isfinite(total):
        raise ValueError("sum must be finite")
    return {"sum": total}


def run_once(settings: Settings) -> bool:
    """Claim and report one attempt; return False when the queue is empty."""
    attempt = claim(settings)
    if attempt is None:
        return False

    if attempt["job_type"] != "add_numbers":
        outcome = "fail"
        payload = {
            "error": {
                "code": "UNSUPPORTED_JOB_TYPE",
                "message": "This worker only supports add_numbers",
            }
        }
    else:
        try:
            result = add_numbers(attempt["params"])
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
        logger.info("add_numbers worker started; press Ctrl+C to stop")
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
