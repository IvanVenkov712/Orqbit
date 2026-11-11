from datetime import datetime, timedelta
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

import execution
import heartbeat
import worker


def test_computation_continues_beyond_initial_lease(
    monkeypatch,
    settings,
    attempt,
    clock,
    slow_computation,
):
    deadline = datetime.fromisoformat(attempt["lease_expires_at"])
    initial_deadline = deadline

    def renew(settings, path):
        nonlocal deadline
        assert path == "workers/17/heartbeat"
        assert clock.now < deadline
        deadline = max(deadline, clock.now + timedelta(seconds=6))
        return {"lease_expires_at": deadline.isoformat()}

    report = Mock()
    monkeypatch.setattr(heartbeat, "post", renew)
    monkeypatch.setattr(execution, "post", report)
    execution.process_attempt(settings, attempt)

    assert slow_computation == [3, 4, 5]
    assert initial_deadline < clock.now < deadline
    report.assert_called_once_with(
        settings,
        "workers/17/succeed",
        {"result": {"limit": 12, "count": 5}},
    )


@pytest.mark.parametrize(
    "error",
    [
        HTTPError("heartbeat", 400, "Lease expired", {}, None),
        HTTPError("heartbeat", 404, "Attempt not found", {}, None),
        HTTPError("heartbeat", 401, "Invalid key", {}, None),
        TimeoutError("private diagnostics"),
    ],
)
def test_ownership_loss_stops_computation_without_outcome(
    monkeypatch,
    settings,
    attempt,
    clock,
    slow_computation,
    caplog,
    error,
):
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "claim", Mock(return_value=attempt))
    renew = Mock(
        side_effect=[
            {"lease_expires_at": attempt["lease_expires_at"]},
            error,
        ]
    )
    report = Mock()
    monkeypatch.setattr(heartbeat, "post", renew)
    monkeypatch.setattr(execution, "post", report)

    assert worker.main() == 1
    assert slow_computation == [3, 4]
    assert renew.call_count == 2
    report.assert_not_called()
    assert "without reporting an outcome" in caplog.text
    assert "private" not in caplog.text


def test_expired_claim_does_not_start_computation(
    monkeypatch, settings, attempt, clock
):
    attempt["lease_expires_at"] = clock.now.isoformat()
    compute = Mock()
    report = Mock()
    monkeypatch.setattr(execution, "count_prime_batches", compute)
    monkeypatch.setattr(execution, "post", report)

    with pytest.raises(heartbeat.LeaseLost):
        execution.process_attempt(settings, attempt)
    compute.assert_not_called()
    report.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"lease_expires_at": "invalid"},
        {"lease_expires_at": None},
        {"lease_expires_at": "2030-01-01T00:00:00"},
    ],
)
def test_invalid_deadline_is_ownership_loss(response):
    with pytest.raises(heartbeat.LeaseLost):
        heartbeat.read_deadline(response, 17)


def test_batch_that_exceeds_lease_stops_without_renewal_or_outcome(
    monkeypatch,
    settings,
    attempt,
    clock,
):
    def slow_batch(limit, batch_size):
        clock.advance(20)
        yield 3

    renew, report = Mock(), Mock()
    monkeypatch.setattr(execution, "count_prime_batches", slow_batch)
    monkeypatch.setattr(heartbeat, "post", renew)
    monkeypatch.setattr(execution, "post", report)

    with pytest.raises(heartbeat.LeaseLost):
        execution.process_attempt(settings, attempt)
    renew.assert_not_called()
    report.assert_not_called()
