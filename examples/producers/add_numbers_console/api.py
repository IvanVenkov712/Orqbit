"""HTTP requests to Orqbit's public producer API."""

import json
from urllib.request import Request, urlopen

from settings import Settings


def submit_job(
    settings: Settings, numbers: list[int | float], idempotency_key: str
) -> dict:
    payload = {
        "job_type": "add_numbers",
        "params": {"numbers": numbers},
        "permission_policy": "PRIVATE",
    }
    request = Request(
        f"{str(settings.api_url).rstrip('/')}/producer/jobs",
        data=json.dumps(payload, allow_nan=False).encode(),
        headers={
            "X-API-Key": settings.api_key.get_secret_value(),
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=settings.request_timeout) as response:
        return json.load(response)


def get_job(settings: Settings, job_id: int) -> dict:
    request = Request(
        f"{str(settings.api_url).rstrip('/')}/producer/jobs/{job_id}",
        headers={"X-API-Key": settings.api_key.get_secret_value()},
        method="GET",
    )
    with urlopen(request, timeout=settings.request_timeout) as response:
        return json.load(response)
