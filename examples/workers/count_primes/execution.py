"""Count primes cooperatively, then report the attempt's outcome."""

import time

from api import post
from heartbeat import read_deadline, remaining_lease_seconds, renew_lease
from primes import count_prime_batches, validate_limit
from settings import Settings


def execute(settings: Settings, attempt: dict) -> dict:
    limit = validate_limit(attempt["params"])
    attempt_id = attempt["id"]
    deadline = read_deadline(attempt, attempt_id)
    remaining = remaining_lease_seconds(deadline, attempt_id)
    renew_at = time.monotonic() + min(settings.heartbeat_interval, remaining / 3)

    count = 0
    for count in count_prime_batches(limit, settings.batch_size):
        remaining_lease_seconds(deadline, attempt_id)
        if time.monotonic() >= renew_at:
            deadline = renew_lease(settings, attempt_id)
            remaining = remaining_lease_seconds(deadline, attempt_id)
            renew_at = time.monotonic() + min(
                settings.heartbeat_interval, remaining / 3
            )

    remaining_lease_seconds(deadline, attempt_id)
    return {"limit": limit, "count": count}


def process_attempt(settings: Settings, attempt: dict) -> None:
    attempt_id = attempt["id"]
    if attempt["job_type"] != "count_primes":
        outcome = "fail"
        payload = {
            "error": {
                "code": "UNSUPPORTED_JOB_TYPE",
                "message": "This worker only supports count_primes",
            }
        }
    else:
        try:
            result = execute(settings, attempt)
        except ValueError as exc:
            outcome = "fail"
            payload = {"error": {"code": "INVALID_PARAMS", "message": str(exc)}}
        else:
            outcome = "succeed"
            payload = {"result": result}

    post(settings, f"workers/{attempt_id}/{outcome}", payload)
