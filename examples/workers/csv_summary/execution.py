"""Summarize one CSV attempt and report its outcome."""

from api import post
from settings import Settings
from summary import summarize_csv


def process_attempt(settings: Settings, attempt: dict) -> None:
    attempt_id = attempt["id"]
    if attempt["job_type"] != "csv_summary":
        outcome = "fail"
        payload = {
            "error": {
                "code": "UNSUPPORTED_JOB_TYPE",
                "message": "This worker only supports csv_summary",
            }
        }
    else:
        try:
            result = summarize_csv(attempt["params"])
        except ValueError as exc:
            outcome = "fail"
            payload = {"error": {"code": "INVALID_PARAMS", "message": str(exc)}}
        else:
            outcome = "succeed"
            payload = {"result": result}

    post(settings, f"workers/{attempt_id}/{outcome}", payload)
