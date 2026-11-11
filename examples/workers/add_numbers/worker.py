"""Independent example worker for the add_numbers job type."""

import json
import logging
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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
    heartbeat_interval: float = Field(default=10, gt=0, allow_inf_nan=False)
    execution_delay: float = Field(default=0, ge=0, allow_inf_nan=False)


class LeaseLost(Exception):
    """The worker can no longer confirm ownership of the attempt."""


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


def post(settings: Settings, path: str, payload: dict | None = None) -> dict:
    request = Request(
        f"{str(settings.api_url).rstrip('/')}/{path}",
        data=None if payload is None else json.dumps(payload, allow_nan=False).encode(),
        headers={
            "X-API-Key": settings.api_key.get_secret_value(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=settings.request_timeout) as response:
        return json.load(response)


def execute_with_heartbeats(settings: Settings, attempt: dict) -> dict:
    attempt_id = attempt["id"]
    deadline = datetime.fromisoformat(attempt["lease_expires_at"])
    stopped = Event()
    heartbeat_failed = False

    def heartbeat() -> None:
        nonlocal deadline, heartbeat_failed
        try:
            while not stopped.is_set():
                remaining = (deadline - datetime.now(UTC)).total_seconds()
                if remaining <= 0:
                    raise LeaseLost("Lease deadline reached")
                # Adapt to both the initial lease and each returned renewal window.
                if stopped.wait(min(settings.heartbeat_interval, remaining / 3)):
                    return
                renewed = post(settings, f"workers/{attempt_id}/heartbeat")
                deadline = datetime.fromisoformat(renewed["lease_expires_at"])
                logger.info(
                    "Renewed lease for attempt %s until %s", attempt_id, deadline
                )
        except Exception:
            # A failed heartbeat thread must never silently allow outcome reporting.
            heartbeat_failed = True
            stopped.set()

    thread = Thread(target=heartbeat, name=f"heartbeat-{attempt_id}")
    thread.start()
    try:
        if stopped.wait(settings.execution_delay):
            raise LeaseLost("Heartbeat failed")
        return add_numbers(attempt["params"])
    finally:
        stopped.set()
        thread.join()
        # Join before reporting, so a heartbeat cannot race with a terminal outcome.
        if heartbeat_failed or datetime.now(UTC) >= deadline:
            raise LeaseLost(
                f"Ownership of attempt {attempt_id} could not be confirmed; "
                "outcome discarded; worker stopped"
            ) from None


def run_once(settings: Settings) -> bool:
    """Claim and report one attempt; return False when the queue is empty."""
    try:
        attempt = post(settings, "workers/claim")
    except HTTPError as exc:
        if exc.code == 404 and json.load(exc).get("detail") == "No jobs were found":
            return False
        raise

    attempt_id = attempt["id"]
    if attempt["job_type"] != "add_numbers":
        post(
            settings,
            f"workers/{attempt_id}/fail",
            {
                "error": {
                    "code": "UNSUPPORTED_JOB_TYPE",
                    "message": "This worker only supports add_numbers",
                }
            },
        )
    else:
        try:
            result = execute_with_heartbeats(settings, attempt)
        except ValueError as exc:
            post(
                settings,
                f"workers/{attempt_id}/fail",
                {
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": str(exc),
                    }
                },
            )
        else:
            post(settings, f"workers/{attempt_id}/succeed", {"result": result})

    logger.info("Reported outcome for attempt %s", attempt_id)
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
    except LeaseLost as exc:
        logger.error("%s", exc)
    except HTTPError as exc:
        logger.error("API request failed with HTTP %s; worker stopped", exc.code)
    except (URLError, OSError, TimeoutError):
        logger.error("API connection failed; worker stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
