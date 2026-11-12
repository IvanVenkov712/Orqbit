"""Submit an add_numbers job and optionally wait for its outcome."""

import argparse
import json
import math
import sys
import time
from urllib.error import HTTPError, URLError
from uuid import uuid4

from pydantic import ValidationError

from api import get_job, submit_job
from settings import Settings


def number(value: str) -> int | float:
    try:
        parsed = json.loads(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a finite number") from None
    if type(parsed) not in (int, float) or (
        isinstance(parsed, float) and not math.isfinite(parsed)
    ):
        raise argparse.ArgumentTypeError("expected a finite number")
    return parsed


def positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected positive finite seconds") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("expected positive finite seconds")
    return seconds


def submission_key(value: str) -> str:
    if (
        not 1 <= len(value) <= 100
        or not value.strip()
        or any(ord(char) < 32 or ord(char) > 126 for char in value)
    ):
        raise argparse.ArgumentTypeError(
            "expected 1-100 printable ASCII characters, not only spaces"
        )
    return value


def wait_for_job(settings: Settings, job: dict, timeout: float) -> dict | None:
    """Poll until terminal; return None if the local waiting period expires."""
    deadline = time.monotonic() + timeout
    while job["status"] not in ("SUCCEEDED", "FAILED"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        job = get_job(
            settings, job["id"], timeout=min(settings.request_timeout, remaining)
        )
        if job["status"] not in ("SUCCEEDED", "FAILED"):
            time.sleep(min(settings.poll_interval, max(0, deadline - time.monotonic())))
    return job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numbers", nargs="+", type=number, help="finite JSON numbers")
    parser.add_argument(
        "--idempotency-key",
        type=submission_key,
        help="reuse for an identical submission",
    )
    parser.add_argument("--wait", action="store_true", help="wait for the job outcome")
    parser.add_argument(
        "--wait-timeout",
        type=positive_seconds,
        default=60,
        help="maximum local waiting period in seconds (default: 60)",
    )
    args = parser.parse_args(argv)

    try:
        settings = Settings()
        key = args.idempotency_key or str(uuid4())
        print(f"Idempotency-Key: {key}", file=sys.stderr, flush=True)
        job = submit_job(settings, args.numbers, key)
        print(f"job_id: {job['id']}", flush=True)
        if not args.wait:
            return 0
        job = wait_for_job(settings, job, args.wait_timeout)
        if job is None:
            print("Waiting period expired; the job was not cancelled.", file=sys.stderr)
            return 1
        print(f"status: {job['status']}")
        field = "result" if job["status"] == "SUCCEEDED" else "error"
        print(f"{field}: {json.dumps(job[field], ensure_ascii=True)}")
        return 0 if job["status"] == "SUCCEEDED" else 1
    except ValidationError:
        print(
            "Invalid producer configuration; check the producer's .env.",
            file=sys.stderr,
        )
    except HTTPError as exc:
        print(f"API request failed with HTTP {exc.code}.", file=sys.stderr)
    except (URLError, OSError, TimeoutError):
        print(
            "API connection failed. If submission was attempted, repeat with the same "
            "--idempotency-key and numbers.",
            file=sys.stderr,
        )
    except (ValueError, KeyError, TypeError):
        print("Invalid API response.", file=sys.stderr)
    except KeyboardInterrupt:
        print("Producer stopped; submitted jobs are not cancelled.", file=sys.stderr)
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
