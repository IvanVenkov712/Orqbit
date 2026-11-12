"""HTTP requests to Orqbit's public worker API."""

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from settings import Settings


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


def claim(settings: Settings) -> dict | None:
    try:
        return post(settings, "workers/claim")
    except HTTPError as exc:
        if exc.code == 404 and json.load(exc).get("detail") == "No jobs were found":
            return None
        raise
