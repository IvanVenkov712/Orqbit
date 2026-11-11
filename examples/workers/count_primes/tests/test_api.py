import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

import api


@pytest.mark.parametrize("payload", [None, {"result": {"sum": 5}}])
def test_post_uses_worker_key_and_json(monkeypatch, settings, payload):
    path = "workers/claim" if payload is None else "workers/17/succeed"

    def respond(request, timeout):
        assert request.get_method() == "POST"
        assert request.full_url == f"http://localhost:8000/{path}"
        assert request.get_header("X-api-key") == "worker-key"
        assert timeout == settings.request_timeout
        assert request.data == (
            None if payload is None else json.dumps(payload).encode()
        )
        return BytesIO(b'{"Status": "200 OK"}')

    monkeypatch.setattr(api, "urlopen", respond)
    assert api.post(settings, path, payload) == {"Status": "200 OK"}


@pytest.mark.parametrize(
    "status,detail",
    [(404, "No jobs were found"), (401, "Invalid key"), (404, "Attempt not found")],
)
def test_claim_distinguishes_empty_queue_from_errors(
    monkeypatch, settings, status, detail
):
    def respond(request, timeout):
        assert request.full_url.endswith("/workers/claim")
        assert request.data is None
        raise HTTPError(
            request.full_url,
            status,
            "error",
            {},
            BytesIO(json.dumps({"detail": detail}).encode()),
        )

    monkeypatch.setattr(api, "urlopen", respond)
    if detail == "No jobs were found":
        assert api.claim(settings) is None
    else:
        with pytest.raises(HTTPError):
            api.claim(settings)
