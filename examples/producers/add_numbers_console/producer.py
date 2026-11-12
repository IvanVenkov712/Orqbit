"""Continuously accept numbers and report independently completed additions."""

import json
import math
import sys
from queue import Empty, Queue
from threading import Event, Thread
from urllib.error import HTTPError, URLError
from uuid import uuid4

from pydantic import ValidationError

from api import get_job, submit_job
from settings import Settings


def parse_numbers(line: str) -> list[int | float]:
    try:
        numbers = [json.loads(token) for token in line.split()]
    except ValueError:
        raise ValueError("Enter finite numbers separated by spaces.") from None
    if not numbers or any(
        type(number) not in (int, float)
        or (isinstance(number, float) and not math.isfinite(number))
        for number in numbers
    ):
        raise ValueError("Enter finite numbers separated by spaces.")
    return numbers


def process_once(
    settings: Settings,
    submissions: Queue,
    pending: dict[str, list[int | float]],
    jobs: dict[int, list[int | float]],
    stop: Event,
) -> None:
    """Submit queued/retryable requests and inspect this session's active jobs."""
    while not stop.is_set():
        try:
            key, numbers = submissions.get_nowait()
        except Empty:
            break
        pending[key] = numbers

    for key, numbers in list(pending.items()):
        if stop.is_set():
            return
        try:
            job = submit_job(settings, numbers, key)
            job_id = job["id"]
        except HTTPError as exc:
            retry = exc.code in (408, 429) or exc.code >= 500
            message = "will retry automatically" if retry else "submission rejected"
            print(
                f"Submission HTTP {exc.code}; {message}.", file=sys.stderr, flush=True
            )
            exc.close()
            if not retry:
                del pending[key]
            continue
        except (URLError, OSError, ValueError, KeyError, TypeError):
            print(
                "Submission response unavailable; will retry automatically.",
                file=sys.stderr,
                flush=True,
            )
            continue
        jobs[job_id] = numbers
        del pending[key]
        if not stop.is_set():
            print(f"Submitted job {job_id}.", flush=True)

    for job_id, numbers in list(jobs.items()):
        if stop.is_set():
            return
        try:
            job = get_job(settings, job_id)
            if job["status"] == "SUCCEEDED":
                expression = " + ".join(str(number) for number in numbers)
                message = f"{expression} = {job['result']['sum']}"
            elif job["status"] == "FAILED":
                message = f"Job {job_id} failed: {json.dumps(job['error'])}"
            else:
                continue
        except HTTPError as exc:
            print(
                f"Job {job_id}: HTTP {exc.code}; will check again.",
                file=sys.stderr,
                flush=True,
            )
            exc.close()
            continue
        except (URLError, OSError, ValueError, KeyError, TypeError):
            print(
                f"Job {job_id}: response unavailable; will check again.",
                file=sys.stderr,
                flush=True,
            )
            continue
        if stop.is_set():
            return
        print(message, flush=True)
        del jobs[job_id]


def run(settings: Settings, submissions: Queue, stop: Event) -> None:
    pending: dict[str, list[int | float]] = {}
    jobs: dict[int, list[int | float]] = {}
    while not stop.is_set():
        process_once(settings, submissions, pending, jobs, stop)
        stop.wait(settings.poll_interval)


def main() -> int:
    try:
        settings = Settings()
    except ValidationError:
        print(
            "Invalid producer configuration; check the producer's .env.",
            file=sys.stderr,
        )
        return 1

    submissions = Queue()
    stop = Event()
    worker = Thread(target=run, args=(settings, submissions, stop), daemon=True)
    try:
        worker.start()
        print("Enter numbers on each line. Press Ctrl+C to stop.", flush=True)
        while True:
            line = input()
            if not line.strip():
                continue
            try:
                numbers = parse_numbers(line)
            except ValueError as exc:
                print(str(exc), file=sys.stderr, flush=True)
                continue
            submissions.put((str(uuid4()), numbers))
    except KeyboardInterrupt:
        return 130
    except EOFError:
        return 0
    finally:
        stop.set()
        if worker.ident is not None:
            worker.join(timeout=settings.request_timeout)
        print("\nProducer stopped; submitted jobs are not cancelled.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
