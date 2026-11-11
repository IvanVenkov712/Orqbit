from unittest.mock import Mock
from urllib.error import HTTPError

import worker


def test_configured_delay_then_report(monkeypatch, settings, attempt):
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))
    pause = Mock()
    post = Mock()
    monkeypatch.setattr(worker.time, "sleep", pause)
    monkeypatch.setattr(worker, "post", post)

    assert worker.run_once(settings) is True
    pause.assert_called_once_with(12)
    post.assert_called_once_with(
        settings,
        "workers/17/succeed",
        {"result": {"waited_seconds": 12}},
    )


def test_empty_queue_does_not_sleep_or_report(monkeypatch, settings):
    monkeypatch.setattr(worker, "claim", Mock(return_value=None))
    pause, post = Mock(), Mock()
    monkeypatch.setattr(worker.time, "sleep", pause)
    monkeypatch.setattr(worker, "post", post)

    assert worker.run_once(settings) is False
    pause.assert_not_called()
    post.assert_not_called()


def test_unsupported_type_does_not_wait(monkeypatch, settings, attempt):
    attempt["job_type"] = "unknown"
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))
    pause, post = Mock(), Mock()
    monkeypatch.setattr(worker.time, "sleep", pause)
    monkeypatch.setattr(worker, "post", post)

    assert worker.run_once(settings) is True
    pause.assert_not_called()
    assert post.call_args.args[1] == "workers/17/fail"


def test_expired_outcome_stops_worker_without_retry(
    monkeypatch, settings, attempt, caplog
):
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))
    monkeypatch.setattr(worker.time, "sleep", Mock())
    post = Mock(
        side_effect=HTTPError("succeed", 400, "The lease has expired", {}, None)
    )
    monkeypatch.setattr(worker, "post", post)

    assert worker.main() == 1
    assert post.call_count == 1
    assert post.call_args.args[1] == "workers/17/succeed"
    assert "HTTP 400" in caplog.text
    assert "Reported outcome" not in caplog.text
