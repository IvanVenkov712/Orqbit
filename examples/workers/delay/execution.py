"""Execute and report a single delay attempt."""

import time

from api import post
from settings import Settings


def process_attempt(settings: Settings, attempt: dict) -> None:
    """Reject unsupported work, otherwise wait and report success."""
    attempt_id = attempt["id"]
    if attempt["job_type"] != "delay":
        post(
            settings,
            f"workers/{attempt_id}/fail",
            {
                "error": {
                    "code": "UNSUPPORTED_JOB_TYPE",
                    "message": "This worker only supports delay",
                }
            },
        )
        return

    time.sleep(settings.execution_delay)
    post(
        settings,
        f"workers/{attempt_id}/succeed",
        {"result": {"waited_seconds": settings.execution_delay}},
    )
