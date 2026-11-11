"""Execute and report a single delay_with_heartbeat attempt."""

from api import post
from heartbeat import wait_with_heartbeats
from settings import Settings


def process_attempt(settings: Settings, attempt: dict) -> None:
    """Reject unsupported work, otherwise wait and report success."""
    attempt_id = attempt["id"]
    if attempt["job_type"] != "delay_with_heartbeat":
        post(
            settings,
            f"workers/{attempt_id}/fail",
            {
                "error": {
                    "code": "UNSUPPORTED_JOB_TYPE",
                    "message": "This worker only supports delay_with_heartbeat",
                }
            },
        )
        return

    wait_with_heartbeats(settings, attempt)
    post(
        settings,
        f"workers/{attempt_id}/succeed",
        {"result": {"waited_seconds": settings.execution_delay}},
    )
