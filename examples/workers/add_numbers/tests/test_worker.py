import importlib.util
import json
import logging
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Event, current_thread, main_thread
from urllib.error import HTTPError

import pytest

import worker


def test_settings_read_adjacent_env_from_another_directory(tmp_path, monkeypatch):
    for name in (
        "API_KEY",
        "API_URL",
        "POLL_INTERVAL",
        "REQUEST_TIMEOUT",
        "HEARTBEAT_INTERVAL",
        "EXECUTION_DELAY",
    ):
        monkeypatch.delenv(name, raising=False)
    script = tmp_path / "worker.py"
    script.write_text(
        Path(worker.__file__).read_text(encoding="utf-8"), encoding="utf-8"
    )
    script.with_name(".env").write_text(
        "API_KEY=worker-key\nAPI_URL=http://localhost:8123\n"
        "POLL_INTERVAL=3\nREQUEST_TIMEOUT=5\nHEARTBEAT_INTERVAL=4\nEXECUTION_DELAY=15\n",
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
    assert settings.heartbeat_interval == 4
    assert settings.execution_delay == 15
    monkeypatch.setenv("API_KEY", "environment-key")
    assert relocated_worker.Settings().api_key.get_secret_value() == "environment-key"


@pytest.mark.parametrize("numbers,total", [([2, 3, 5], 10), ([-2, 0.5], -1.5), ([], 0)])
def test_add_numbers(numbers, total):
    assert worker.add_numbers({"numbers": numbers}) == {"sum": total}


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"numbers": [True]},
        {"numbers": ["2"]},
        {"numbers": None},
        {"numbers": "123"},
        {"numbers": [float("nan")]},
        {"numbers": [float("inf")]},
        {"numbers": [float("-inf")]},
    ],
)
def test_add_numbers_rejects_invalid_input(params):
    with pytest.raises(ValueError):
        worker.add_numbers(params)


@pytest.mark.parametrize(
    ("numbers", "message"),
    [
        ([1e308, 1e308], "sum must be finite"),
        ([10**400, 1.0], "sum is outside the supported numeric range"),
    ],
)
def test_add_numbers_rejects_overflow(numbers, message):
    with pytest.raises(ValueError, match=message):
        worker.add_numbers({"numbers": numbers})


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
            {
                "id": 17,
                "job_id": 42,
                "job_type": "add_numbers",
                "params": params,
                "lease_expires_at": (
                    datetime.now(UTC) + timedelta(minutes=2)
                ).isoformat(),
            }
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


def test_unsupported_job_type_reports_failure_without_execution(monkeypatch):
    from unittest.mock import Mock

    settings = worker.Settings(
        _env_file=None, api_key="worker-key", api_url="http://localhost:8000"
    )
    post = Mock(side_effect=[{"id": 17, "job_type": "unknown", "params": {}}, {}])
    execute = Mock(side_effect=AssertionError("Unsupported job must not execute"))
    monkeypatch.setattr(worker, "post", post)
    monkeypatch.setattr(worker, "add_numbers", execute)
    assert worker.run_once(settings) is True
    assert post.call_count == 2
    post.assert_called_with(
        settings,
        "workers/17/fail",
        {
            "error": {
                "code": "UNSUPPORTED_JOB_TYPE",
                "message": "This worker only supports add_numbers",
            }
        },
    )
    execute.assert_not_called()


def test_report_timeout_stops_worker_without_reporting_success_or_retrying(
    monkeypatch, caplog
):
    from unittest.mock import Mock

    settings = worker.Settings(
        _env_file=None, api_key="private-key", api_url="http://localhost:8000"
    )
    caplog.set_level(logging.INFO, logger=worker.__name__)
    requests = []

    def respond(request, timeout):
        requests.append(request)
        if len(requests) == 1:
            return BytesIO(
                json.dumps(
                    {
                        "id": 17,
                        "job_type": "add_numbers",
                        "params": {"numbers": [2, 3]},
                        "lease_expires_at": (
                            datetime.now(UTC) + timedelta(minutes=2)
                        ).isoformat(),
                    }
                ).encode()
            )
        raise TimeoutError("private connection diagnostics")

    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "urlopen", respond)
    pause = Mock()
    monkeypatch.setattr(worker.time, "sleep", pause)
    assert worker.main() == 1
    assert len(requests) == 2
    assert requests[1].full_url.endswith("/workers/17/succeed")
    assert json.loads(requests[1].data) == {"result": {"sum": 5}}
    pause.assert_not_called()
    assert "API connection failed; worker stopped" in caplog.text
    assert "Reported outcome" not in caplog.text
    assert "private" not in caplog.text


@pytest.fixture
def heartbeat_control(monkeypatch):
    """Drive the real heartbeat thread with events and a virtual clock, not sleeps."""
    clock = {"now": datetime.now(UTC)}
    ready = Event()
    tick = Event()
    waits = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    class ControlledEvent(Event):
        def wait(self, timeout=None):
            if current_thread() is main_thread():
                return super().wait(timeout)
            waits.append(timeout)
            ready.set()
            assert tick.wait(5), "Test did not release the heartbeat thread"
            tick.clear()
            return self.is_set()

        def set(self):
            super().set()
            tick.set()

    stopped = ControlledEvent()
    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(worker, "Event", lambda: stopped)
    return clock, ready, tick, stopped, waits


@pytest.mark.parametrize("numbers,outcome", [([2, 3, 5], "succeed"), ([True], "fail")])
def test_heartbeats_keep_slow_execution_alive_beyond_initial_lease(
    monkeypatch, heartbeat_control, numbers, outcome
):
    clock, ready, tick, stopped, waits = heartbeat_control
    settings = worker.Settings(
        _env_file=None, api_key="worker-key", api_url="http://localhost:8000"
    )
    initial_deadline = clock["now"] + timedelta(seconds=10)
    deadline = initial_deadline
    requests = []

    def respond(request, timeout):
        nonlocal deadline
        assert request.get_method() == "POST"
        assert request.get_header("X-api-key") == "worker-key"
        requests.append(request)
        if request.full_url.endswith("/claim"):
            response = {
                "id": 17,
                "job_type": "add_numbers",
                "params": {"numbers": numbers},
                "lease_expires_at": deadline.isoformat(),
            }
        elif request.full_url.endswith("/heartbeat"):
            assert request.data is None
            assert clock["now"] < deadline
            deadline = max(deadline, clock["now"] + timedelta(seconds=6))
            response = {"lease_expires_at": deadline.isoformat()}
        else:
            assert stopped.is_set()
            assert initial_deadline < clock["now"] < deadline
            response = {"Status": "200 OK"}
        return BytesIO(json.dumps(response).encode())

    original = worker.add_numbers

    def slow_add_numbers(params):
        for _ in range(3):
            assert ready.wait(5)
            ready.clear()
            clock["now"] += timedelta(seconds=4)
            tick.set()
        assert ready.wait(5)
        return original(params)

    monkeypatch.setattr(worker, "urlopen", respond)
    monkeypatch.setattr(worker, "add_numbers", slow_add_numbers)
    assert worker.run_once(settings) is True
    assert [request.full_url.rsplit("/", 1)[-1] for request in requests] == [
        "claim",
        "heartbeat",
        "heartbeat",
        "heartbeat",
        outcome,
    ]
    assert waits == pytest.approx([10 / 3, 2, 2, 2])
    payload = json.loads(requests[-1].data)
    if outcome == "succeed":
        assert payload == {"result": {"sum": 10}}
    else:
        assert payload["error"]["code"] == "INVALID_PARAMS"


@pytest.mark.parametrize(
    "status,detail",
    [
        (400, "The lease has expired"),
        (400, "The attempt is not running"),
        (404, "Attempt not found"),
        (401, "Invalid key"),
        (500, "private server diagnostics"),
        (None, "private connection diagnostics"),
    ],
)
def test_heartbeat_failure_interrupts_delay_without_reporting_or_retrying(
    monkeypatch, heartbeat_control, caplog, status, detail
):
    from unittest.mock import Mock

    clock, _, tick, stopped, _ = heartbeat_control
    settings = worker.Settings(
        _env_file=None,
        api_key="private-key",
        api_url="http://localhost:8000",
        execution_delay=3600,
    )
    paths = []

    def respond(request, timeout):
        paths.append(request.full_url.rsplit("/", 1)[-1])
        if paths == ["claim"]:
            tick.set()
            return BytesIO(
                json.dumps(
                    {
                        "id": 17,
                        "job_type": "add_numbers",
                        "params": {"numbers": [2, 3]},
                        "lease_expires_at": (
                            clock["now"] + timedelta(seconds=10)
                        ).isoformat(),
                    }
                ).encode()
            )
        if status is None:
            raise TimeoutError(detail)
        raise HTTPError(
            request.full_url,
            status,
            "error",
            {},
            BytesIO(json.dumps({"detail": detail}).encode()),
        )

    execute = Mock()
    caplog.set_level(logging.INFO, logger=worker.__name__)
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "urlopen", respond)
    monkeypatch.setattr(worker, "add_numbers", execute)
    assert worker.main() == 1
    assert stopped.is_set()
    assert paths == ["claim", "heartbeat"]
    execute.assert_not_called()
    assert "Ownership of attempt 17 could not be confirmed" in caplog.text
    assert "outcome discarded; worker stopped" in caplog.text
    assert "Reported outcome" not in caplog.text
    assert "private" not in caplog.text


@pytest.mark.parametrize("invalid_params", [False, True])
def test_ownership_loss_during_handler_discards_result_or_error(
    monkeypatch, heartbeat_control, invalid_params
):
    from unittest.mock import Mock

    clock, ready, tick, stopped, _ = heartbeat_control
    settings = worker.Settings(
        _env_file=None, api_key="worker-key", api_url="http://localhost:8000"
    )
    post = Mock(
        side_effect=[
            {
                "id": 17,
                "job_type": "add_numbers",
                "params": {},
                "lease_expires_at": (clock["now"] + timedelta(seconds=10)).isoformat(),
            },
            HTTPError("heartbeat", 404, "Attempt not found", {}, None),
        ]
    )

    def slow_add_numbers(params):
        assert ready.wait(5)
        tick.set()
        assert stopped.wait(5)
        if invalid_params:
            raise ValueError("Invalid numbers")
        return {"sum": 10}

    monkeypatch.setattr(worker, "post", post)
    monkeypatch.setattr(worker, "add_numbers", slow_add_numbers)
    with pytest.raises(worker.LeaseLost, match="outcome discarded"):
        worker.run_once(settings)
    assert post.call_count == 2
    post.assert_called_with(settings, "workers/17/heartbeat")


def test_expiry_before_report_discards_result(monkeypatch, heartbeat_control):
    from unittest.mock import Mock

    clock, _, _, _, _ = heartbeat_control
    deadline = clock["now"] + timedelta(seconds=10)
    settings = worker.Settings(
        _env_file=None, api_key="worker-key", api_url="http://localhost:8000"
    )
    post = Mock(
        return_value={
            "id": 17,
            "job_type": "add_numbers",
            "params": {},
            "lease_expires_at": deadline.isoformat(),
        }
    )

    def execute(params):
        clock["now"] = deadline
        return {"sum": 10}

    monkeypatch.setattr(worker, "post", post)
    monkeypatch.setattr(worker, "add_numbers", execute)
    with pytest.raises(worker.LeaseLost, match="outcome discarded"):
        worker.run_once(settings)
    post.assert_called_once_with(settings, "workers/claim")


@pytest.mark.parametrize(
    "field,value",
    [
        ("heartbeat_interval", 0),
        ("heartbeat_interval", -1),
        ("heartbeat_interval", float("inf")),
        ("execution_delay", -1),
        ("execution_delay", float("nan")),
    ],
)
def test_heartbeat_and_delay_settings_reject_invalid_values(field, value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        worker.Settings(
            _env_file=None,
            api_key="worker-key",
            api_url="http://localhost:8000",
            **{field: value},
        )
