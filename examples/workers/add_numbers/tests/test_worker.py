import importlib.util
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

import worker


def test_settings_read_adjacent_env_from_another_directory(tmp_path, monkeypatch):
    for name in ("API_KEY", "API_URL", "POLL_INTERVAL", "REQUEST_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    script = tmp_path / "worker.py"
    script.write_text(
        Path(worker.__file__).read_text(encoding="utf-8"), encoding="utf-8"
    )
    script.with_name(".env").write_text(
        "API_KEY=worker-key\nAPI_URL=http://localhost:8123\n"
        "POLL_INTERVAL=3\nREQUEST_TIMEOUT=5\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path.parent)
    spec = importlib.util.spec_from_file_location("relocated_worker", script)
    relocated_worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(relocated_worker)
    settings = relocated_worker.Settings()

    assert settings.api_key.get_secret_value() == "worker-key"
    assert str(settings.api_url) == "http://localhost:8123/"
    assert settings.poll_interval == 3
    assert settings.request_timeout == 5
    monkeypatch.setenv("API_KEY", "environment-key")
    assert relocated_worker.Settings().api_key.get_secret_value() == "environment-key"


@pytest.mark.parametrize("numbers,total", [([2, 3, 5], 10), ([-2, 0.5], -1.5), ([], 0)])
def test_add_numbers(numbers, total):
    assert worker.add_numbers({"numbers": numbers}) == {"sum": total}


@pytest.mark.parametrize("params", [{}, {"numbers": [True]}, {"numbers": ["2"]}])
def test_add_numbers_rejects_invalid_input(params):
    with pytest.raises(ValueError):
        worker.add_numbers(params)


@pytest.mark.parametrize(
    "params,outcome,payload",
    [
        ({"numbers": [2, 3, 5]}, "succeed", {"result": {"sum": 10}}),
        (
            {"numbers": [True]},
            "fail",
            {
                "error": {
                    "code": "INVALID_PARAMS",
                    "message": "numbers must be a list of finite numbers",
                }
            },
        ),
    ],
)
def test_claim_and_report_use_worker_key_and_attempt_id(
    monkeypatch, params, outcome, payload
):
    settings = worker.Settings(
        _env_file=None,
        api_key="worker-key",
        api_url="http://localhost:8000",
        request_timeout=7,
    )
    requests = []

    def respond(request, timeout):
        assert request.get_method() == "POST"
        assert request.get_header("X-api-key") == "worker-key"
        assert timeout == 7
        requests.append(request)
        response = (
            {"id": 17, "job_id": 42, "job_type": "add_numbers", "params": params}
            if len(requests) == 1
            else {"Status": "200 OK"}
        )
        return BytesIO(json.dumps(response).encode())

    monkeypatch.setattr(worker, "urlopen", respond)
    assert worker.run_once(settings) is True
    assert requests[0].full_url == "http://localhost:8000/workers/claim"
    assert requests[0].data is None
    assert requests[1].full_url == f"http://localhost:8000/workers/17/{outcome}"
    assert json.loads(requests[1].data) == payload


@pytest.mark.parametrize(
    "status,detail", [(404, "No jobs were found"), (401, "Invalid key")]
)
def test_empty_queue_is_distinct_from_api_errors(monkeypatch, status, detail):
    settings = worker.Settings(
        _env_file=None, api_key="worker-key", api_url="http://localhost:8000"
    )

    def respond(request, timeout):
        raise HTTPError(
            request.full_url,
            status,
            "error",
            {},
            BytesIO(json.dumps({"detail": detail}).encode()),
        )

    monkeypatch.setattr(worker, "urlopen", respond)
    if status == 404:
        assert worker.run_once(settings) is False
    else:
        with pytest.raises(HTTPError):
            worker.run_once(settings)
