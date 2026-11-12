import importlib.util
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, call
from urllib.error import HTTPError, URLError
from uuid import UUID

import pytest
from pydantic import ValidationError

import api
import producer
import settings as configuration


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("API_KEY", "API_URL", "POLL_INTERVAL", "REQUEST_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(monkeypatch):
    settings = configuration.Settings(
        _env_file=None, api_key="producer-key", api_url="http://localhost:8000"
    )
    monkeypatch.setattr(producer, "Settings", lambda: settings)
    return settings


def test_submit_uses_producer_auth_idempotency_and_private_payload(
    monkeypatch, settings
):
    def respond(request, timeout):
        assert request.get_method() == "POST"
        assert request.full_url == "http://localhost:8000/producer/jobs"
        assert request.get_header("X-api-key") == "producer-key"
        assert request.get_header("Idempotency-key") == "submission-1"
        assert request.get_header("Content-type") == "application/json"
        assert timeout == settings.request_timeout
        assert json.loads(request.data) == {
            "job_type": "add_numbers",
            "params": {"numbers": [2, -3.5, 5]},
            "permission_policy": "PRIVATE",
        }
        return BytesIO(b'{"id": 42, "status": "PENDING"}')

    monkeypatch.setattr(api, "urlopen", respond)
    assert api.submit_job(settings, [2, -3.5, 5], "submission-1")["id"] == 42


def test_get_uses_producer_route_and_supplied_timeout(monkeypatch, settings):
    def respond(request, timeout):
        assert request.get_method() == "GET"
        assert request.full_url == "http://localhost:8000/producer/jobs/42"
        assert request.get_header("X-api-key") == "producer-key"
        assert request.data is None
        assert timeout == 1.5
        return BytesIO(b'{"id": 42, "status": "SUCCEEDED", "result": {"sum": 10}}')

    monkeypatch.setattr(api, "urlopen", respond)
    assert api.get_job(settings, 42, timeout=1.5)["result"] == {"sum": 10}


def test_submission_prints_key_before_post_and_id_without_polling(
    monkeypatch, settings, capsys
):
    def submit(config, numbers, key):
        assert config is settings
        assert numbers == [2, 3.5, -5]
        assert UUID(key).version == 4
        assert capsys.readouterr().err == f"Idempotency-Key: {key}\n"
        return {"id": 42, "status": "PENDING"}

    monkeypatch.setattr(producer, "submit_job", submit)
    get = Mock()
    monkeypatch.setattr(producer, "get_job", get)
    assert producer.main(["2", "3.5", "-5"]) == 0
    assert capsys.readouterr().out == "job_id: 42\n"
    get.assert_not_called()


def test_explicit_key_is_reused_on_a_later_invocation(monkeypatch, settings, capsys):
    submit = Mock(return_value={"id": 42, "status": "SUCCEEDED", "result": {"sum": 10}})
    get = Mock()
    monkeypatch.setattr(producer, "submit_job", submit)
    monkeypatch.setattr(producer, "get_job", get)
    args = ["--idempotency-key", "original-key", "2", "3", "5"]
    assert producer.main(args) == 0
    assert producer.main(["--wait", *args]) == 0
    assert submit.call_args_list == [call(settings, [2, 3, 5], "original-key")] * 2
    get.assert_not_called()
    assert capsys.readouterr().out.count("job_id: 42") == 2


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["true"],
        ['"2"'],
        ["NaN"],
        ["Infinity"],
        ["1e999"],
        ["[]"],
        ["{}"],
        ["text"],
        ["--wait-timeout", "0", "2"],
        ["--wait-timeout", "nan", "2"],
        ["--wait-timeout", "inf", "2"],
        ["--idempotency-key", " ", "2"],
        ["--idempotency-key", "x" * 101, "2"],
        ["--idempotency-key", "bad\nheader", "2"],
    ],
)
def test_invalid_cli_input_is_rejected_before_submission(monkeypatch, args):
    submit = Mock()
    monkeypatch.setattr(producer, "submit_job", submit)
    with pytest.raises(SystemExit) as exc:
        producer.main(args)
    assert exc.value.code == 2
    submit.assert_not_called()


@pytest.mark.parametrize(
    "status,field,value,exit_code",
    [
        ("SUCCEEDED", "result", {"sum": 10}, 0),
        ("FAILED", "error", {"code": "INVALID_PARAMS", "message": "invalid input"}, 1),
    ],
)
def test_wait_polls_through_pending_and_running_then_prints_outcome(
    monkeypatch, settings, capsys, status, field, value, exit_code
):
    monkeypatch.setattr(
        producer, "submit_job", Mock(return_value={"id": 42, "status": "PENDING"})
    )
    get = Mock(
        side_effect=[
            {"id": 42, "status": "PENDING"},
            {"id": 42, "status": "RUNNING"},
            {"id": 42, "status": status, field: value},
        ]
    )
    monkeypatch.setattr(producer, "get_job", get)
    monkeypatch.setattr(producer.time, "monotonic", lambda: 0)
    pause = Mock()
    monkeypatch.setattr(producer.time, "sleep", pause)
    assert producer.main(["--wait", "2", "3", "5"]) == exit_code
    assert get.call_args_list == [call(settings, 42, timeout=10)] * 3
    assert pause.call_args_list == [call(settings.poll_interval)] * 2
    output = capsys.readouterr().out
    assert "job_id: 42" in output
    assert f"status: {status}" in output
    assert f"{field}: {json.dumps(value)}" in output


def test_local_timeout_bounds_polls_and_does_not_resubmit(
    monkeypatch, settings, capsys
):
    clock = [0.0]

    def advance(seconds):
        clock[0] += seconds

    monkeypatch.setattr(producer.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(producer.time, "sleep", advance)
    submit = Mock(return_value={"id": 42, "status": "PENDING"})
    get = Mock(return_value={"id": 42, "status": "RUNNING"})
    monkeypatch.setattr(producer, "submit_job", submit)
    monkeypatch.setattr(producer, "get_job", get)
    assert producer.main(["--wait", "--wait-timeout", "5", "2"]) == 1
    assert clock[0] == 5
    assert get.call_args_list == [
        call(settings, 42, timeout=5),
        call(settings, 42, timeout=3),
        call(settings, 42, timeout=1),
    ]
    submit.assert_called_once()
    assert "not cancelled" in capsys.readouterr().err


@pytest.mark.parametrize("status", [401, 409, 422, 503])
def test_http_errors_stop_without_retries_or_exposing_response(
    monkeypatch, settings, capsys, status
):
    respond = Mock(
        side_effect=HTTPError(
            "http://private-host", status, "private diagnostics", {}, BytesIO(b"secret")
        )
    )
    monkeypatch.setattr(api, "urlopen", respond)
    assert producer.main(["--idempotency-key", "original-key", "2"]) == 1
    respond.assert_called_once()
    output = capsys.readouterr()
    assert not output.out
    assert f"HTTP {status}" in output.err
    assert "secret" not in output.err
    assert "private" not in output.err


@pytest.mark.parametrize("error", [TimeoutError("secret"), URLError("secret")])
def test_lost_submission_response_preserves_key_without_retry(
    monkeypatch, settings, capsys, error
):
    respond = Mock(side_effect=error)
    monkeypatch.setattr(api, "urlopen", respond)
    assert producer.main(["--idempotency-key", "original-key", "2"]) == 1
    respond.assert_called_once()
    output = capsys.readouterr()
    assert not output.out
    assert "Idempotency-Key: original-key" in output.err
    assert "same --idempotency-key and numbers" in output.err
    assert "secret" not in output.err


def test_keyboard_interrupt_does_not_cancel_job(monkeypatch, settings, capsys):
    monkeypatch.setattr(
        producer, "submit_job", Mock(return_value={"id": 42, "status": "PENDING"})
    )
    monkeypatch.setattr(producer, "get_job", Mock(side_effect=KeyboardInterrupt))
    assert producer.main(["--wait", "2"]) == 130
    assert "not cancelled" in capsys.readouterr().err


def test_invalid_api_response_has_no_traceback(monkeypatch, settings, capsys):
    monkeypatch.setattr(api, "urlopen", Mock(return_value=BytesIO(b"not JSON")))
    assert producer.main(["2"]) == 1
    assert "Invalid API response" in capsys.readouterr().err


@pytest.mark.parametrize("field", ["poll_interval", "request_timeout"])
@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_timing_configuration_must_be_positive_and_finite(field, value):
    with pytest.raises(ValidationError):
        configuration.Settings(
            _env_file=None,
            api_key="producer-key",
            api_url="http://localhost:8000",
            **{field: value},
        )


def test_adjacent_env_is_loaded_from_another_directory_and_environment_wins(
    tmp_path, monkeypatch
):
    script = tmp_path / "settings.py"
    script.write_text(Path(configuration.__file__).read_text(encoding="utf-8"))
    script.with_name(".env").write_text(
        "API_KEY=file-key\nAPI_URL=http://localhost:8123\nPOLL_INTERVAL=3\nREQUEST_TIMEOUT=5\n"
    )
    monkeypatch.chdir(tmp_path.parent)
    spec = importlib.util.spec_from_file_location("relocated_settings", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = module.Settings()
    assert settings.api_key.get_secret_value() == "file-key"
    assert str(settings.api_url) == "http://localhost:8123/"
    assert settings.poll_interval == 3
    assert settings.request_timeout == 5
    monkeypatch.setenv("API_KEY", "environment-key")
    assert module.Settings().api_key.get_secret_value() == "environment-key"


def test_configuration_errors_hide_secrets_and_prevent_submission(monkeypatch, capsys):
    def invalid_settings():
        return configuration.Settings(_env_file=None, api_key="private-key")

    monkeypatch.setattr(producer, "Settings", invalid_settings)
    submit = Mock()
    monkeypatch.setattr(producer, "submit_job", submit)
    assert producer.main(["2"]) == 1
    submit.assert_not_called()
    error = capsys.readouterr().err
    assert "Invalid producer configuration" in error
    assert "private-key" not in error
