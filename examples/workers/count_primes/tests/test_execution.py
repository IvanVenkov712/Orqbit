from unittest.mock import Mock

import pytest

import execution


def test_success_reports_computed_count(monkeypatch, settings, attempt):
    post = Mock()
    monkeypatch.setattr(execution, "post", post)

    execution.process_attempt(settings, attempt)
    post.assert_called_once_with(
        settings,
        "workers/17/succeed",
        {"result": {"limit": 12, "count": 5}},
    )


@pytest.mark.parametrize(
    "job_type,params,code",
    [
        ("unknown", {}, "UNSUPPORTED_JOB_TYPE"),
        ("count_primes", {"limit": True}, "INVALID_PARAMS"),
        ("count_primes", {}, "INVALID_PARAMS"),
    ],
)
def test_invalid_work_reports_failure(
    monkeypatch, settings, attempt, job_type, params, code
):
    attempt.update(job_type=job_type, params=params)
    post = Mock()
    monkeypatch.setattr(execution, "post", post)

    execution.process_attempt(settings, attempt)
    assert post.call_count == 1
    assert post.call_args.args[1] == "workers/17/fail"
    assert post.call_args.args[2]["error"]["code"] == code


def test_lost_success_response_does_not_send_failure(monkeypatch, settings, attempt):
    post = Mock(side_effect=TimeoutError)
    monkeypatch.setattr(execution, "post", post)

    with pytest.raises(TimeoutError):
        execution.process_attempt(settings, attempt)
    assert post.call_count == 1
    assert post.call_args.args[1] == "workers/17/succeed"
