import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

import api


@pytest.mark.parametrize("payload", [None, {"result": {"sum": 5}}])
def test_post_uses_worker_key_and_json(monkeypatch, settings, payload):
    def respond(request, timeout):
        assert request.get_method() == "POST"
        assert request.full_url == "http://localhost:8000/workers/17/heartbeat"
        assert request.get_header("X-api-key") == "worker-key"
        assert timeout == settings.request_timeout
        assert request.data == (
            None if payload is None else json.dumps(payload).encode()
        )
        return BytesIO(b'{"lease_expires_at": "2030-01-01T00:01:00Z"}')

    monkeypatch.setattr(api, "urlopen", respond)
    assert "lease_expires_at" in api.post(settings, "workers/17/heartbeat", payload)


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
