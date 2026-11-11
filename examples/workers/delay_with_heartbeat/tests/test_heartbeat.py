from datetime import timedelta
from unittest.mock import Mock

import pytest

import heartbeat


@pytest.mark.parametrize(
    "response",
    [
        {"lease_expires_at": "2030-01-01T00:00:00Z"},
        {"lease_expires_at": "invalid"},
        {"lease_expires_at": "2030-01-01T00:01:00"},
        {},
    ],
)
def test_unusable_renewal_stops_waiting(
    monkeypatch, settings, attempt, clock, response
):
    post = Mock(return_value=response)
    monkeypatch.setattr(heartbeat, "post", post)

    with pytest.raises(heartbeat.LeaseLost):
        heartbeat.wait_with_heartbeats(settings, attempt)
    post.assert_called_once_with(settings, "workers/17/heartbeat")
    assert clock.elapsed < settings.execution_delay


def test_expired_claim_does_not_wait_or_renew(monkeypatch, settings, attempt, clock):
    attempt["lease_expires_at"] = clock.now.isoformat()
    post = Mock()
    monkeypatch.setattr(heartbeat, "post", post)

    with pytest.raises(heartbeat.LeaseLost):
        heartbeat.wait_with_heartbeats(settings, attempt)
    assert clock.sleeps == []
    post.assert_not_called()


def test_oversleep_past_deadline_does_not_renew(monkeypatch, settings, attempt, clock):
    def oversleep(seconds):
        clock.now += timedelta(seconds=20)

    monkeypatch.setattr(heartbeat.time, "sleep", oversleep)
    post = Mock()
    monkeypatch.setattr(heartbeat, "post", post)

    with pytest.raises(heartbeat.LeaseLost):
        heartbeat.wait_with_heartbeats(settings, attempt)
    post.assert_not_called()


def test_zero_delay_finishes_without_heartbeat(monkeypatch, settings, attempt, clock):
    settings.execution_delay = 0
    post = Mock()
    monkeypatch.setattr(heartbeat, "post", post)

    heartbeat.wait_with_heartbeats(settings, attempt)
    assert clock.sleeps == []
    post.assert_not_called()
