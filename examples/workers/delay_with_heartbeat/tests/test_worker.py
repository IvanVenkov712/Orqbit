import logging
from datetime import datetime, timedelta
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

import worker


def test_long_task_finishes_after_renewed_initial_lease(
    monkeypatch,
    settings,
    attempt,
    clock,
):
    deadline = datetime.fromisoformat(attempt["lease_expires_at"])
    initial_deadline = deadline
    paths = []
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))

    def post(settings, path, payload=None):
        nonlocal deadline
        paths.append(path)
        assert clock.now < deadline
        if path.endswith("/heartbeat"):
            assert payload is None
            deadline = max(deadline, clock.now + timedelta(seconds=6))
            return {"lease_expires_at": deadline.isoformat()}
        assert clock.now > initial_deadline
        assert payload == {"result": {"waited_seconds": 12}}
        return {}

    monkeypatch.setattr(worker, "post", post)
    assert worker.run_once(settings) is True
    assert clock.elapsed == pytest.approx(12)
    assert paths.count("workers/17/heartbeat") >= 2
    assert paths[-1] == "workers/17/succeed"


@pytest.mark.parametrize(
    "error",
    [
        HTTPError("heartbeat", 400, "The lease has expired", {}, None),
        HTTPError("heartbeat", 400, "The attempt is not running", {}, None),
        HTTPError("heartbeat", 404, "Attempt not found", {}, None),
        HTTPError("heartbeat", 401, "Invalid key", {}, None),
        TimeoutError("private diagnostics"),
    ],
)
def test_heartbeat_failure_stops_without_outcome(
    monkeypatch,
    settings,
    attempt,
    clock,
    caplog,
    error,
):
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))
    post = Mock(side_effect=error)
    monkeypatch.setattr(worker, "post", post)
    caplog.set_level(logging.INFO, logger=worker.__name__)

    assert worker.main() == 1
    post.assert_called_once_with(settings, "workers/17/heartbeat")
    assert clock.elapsed < settings.execution_delay
    assert "Ownership of attempt 17 could not be confirmed" in caplog.text
    assert "without reporting an outcome" in caplog.text
    assert "Reported outcome" not in caplog.text
    assert "private" not in caplog.text


def test_empty_queue_does_not_execute_or_report(monkeypatch, settings):
    monkeypatch.setattr(worker, "claim", Mock(return_value=None))
    wait, post = Mock(), Mock()
    monkeypatch.setattr(worker, "wait_with_heartbeats", wait)
    monkeypatch.setattr(worker, "post", post)

    assert worker.run_once(settings) is False
    wait.assert_not_called()
    post.assert_not_called()


def test_unsupported_type_does_not_execute(monkeypatch, settings, attempt):
    attempt["job_type"] = "unknown"
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))
    wait, post = Mock(), Mock()
    monkeypatch.setattr(worker, "wait_with_heartbeats", wait)
    monkeypatch.setattr(worker, "post", post)

    assert worker.run_once(settings) is True
    wait.assert_not_called()
    assert post.call_args.args[1] == "workers/17/fail"
