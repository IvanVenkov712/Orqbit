from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

import worker


def test_claim_processes_one_attempt(monkeypatch, settings, attempt):
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))
    process = Mock()
    monkeypatch.setattr(worker, "process_attempt", process)

    assert worker.run_once(settings) is True
    process.assert_called_once_with(settings, attempt)


def test_empty_queue_does_not_execute(monkeypatch, settings):
    monkeypatch.setattr(worker, "claim", Mock(return_value=None))
    process = Mock()
    monkeypatch.setattr(worker, "process_attempt", process)

    assert worker.run_once(settings) is False
    process.assert_not_called()


def test_polling_pauses_only_when_queue_is_empty(monkeypatch, settings):
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(
        worker, "run_once", Mock(side_effect=[True, False, KeyboardInterrupt])
    )
    pause = Mock()
    monkeypatch.setattr(worker.time, "sleep", pause)

    assert worker.main() == 0
    pause.assert_called_once_with(settings.poll_interval)


@pytest.mark.parametrize(
    "error",
    [
        HTTPError("report", 400, "Lease expired", {}, None),
        TimeoutError("private connection diagnostics"),
    ],
)
def test_processing_error_stops_without_retry(
    monkeypatch, settings, attempt, caplog, error
):
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))
    process = Mock(side_effect=error)
    monkeypatch.setattr(worker, "process_attempt", process)

    assert worker.main() == 1
    process.assert_called_once_with(settings, attempt)
    assert "Reported outcome" not in caplog.text
    assert "private" not in caplog.text
