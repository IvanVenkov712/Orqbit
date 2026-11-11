import logging
from unittest.mock import Mock

import pytest

import worker


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
def test_claim_and_report(monkeypatch, settings, params, outcome, payload):
    monkeypatch.setattr(
        worker,
        "claim",
        Mock(
            return_value={
                "id": 17,
                "job_id": 42,
                "job_type": "add_numbers",
                "params": params,
            }
        ),
    )
    post = Mock()
    monkeypatch.setattr(worker, "post", post)

    assert worker.run_once(settings) is True
    post.assert_called_once_with(settings, f"workers/17/{outcome}", payload)


def test_unsupported_type_does_not_execute(monkeypatch, settings):
    monkeypatch.setattr(
        worker, "claim", Mock(return_value={"id": 17, "job_type": "unknown"})
    )
    execute = Mock()
    post = Mock()
    monkeypatch.setattr(worker, "add_numbers", execute)
    monkeypatch.setattr(worker, "post", post)

    assert worker.run_once(settings) is True
    execute.assert_not_called()
    assert post.call_args.args[1] == "workers/17/fail"
    assert post.call_args.args[2]["error"]["code"] == "UNSUPPORTED_JOB_TYPE"


def test_empty_queue_polls_until_interrupted(monkeypatch, settings):
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "claim", Mock(side_effect=[None, KeyboardInterrupt]))
    pause = Mock()
    monkeypatch.setattr(worker.time, "sleep", pause)

    assert worker.main() == 0
    pause.assert_called_once_with(settings.poll_interval)


def test_report_timeout_stops_without_retry_or_failure_report(
    monkeypatch, settings, caplog
):
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(
        worker,
        "claim",
        Mock(
            return_value={
                "id": 17,
                "job_type": "add_numbers",
                "params": {"numbers": [2, 3]},
            }
        ),
    )
    post = Mock(side_effect=TimeoutError("private diagnostics"))
    monkeypatch.setattr(worker, "post", post)
    caplog.set_level(logging.INFO, logger=worker.__name__)

    assert worker.main() == 1
    post.assert_called_once_with(settings, "workers/17/succeed", {"result": {"sum": 5}})
    assert "API connection failed; worker stopped" in caplog.text
    assert "Reported outcome" not in caplog.text
    assert "private" not in caplog.text
