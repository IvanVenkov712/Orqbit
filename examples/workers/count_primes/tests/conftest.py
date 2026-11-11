from datetime import UTC, datetime, timedelta

import pytest

from settings import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        api_key="worker-key",
        api_url="http://localhost:8000",
        batch_size=4,
        heartbeat_interval=10,
    )


@pytest.fixture
def attempt():
    return {
        "id": 17,
        "job_id": 42,
        "job_type": "count_primes",
        "params": {"limit": 12},
        "lease_expires_at": (datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
    }


@pytest.fixture
def clock(monkeypatch, attempt):
    from types import SimpleNamespace

    import execution
    import heartbeat

    clock = SimpleNamespace(
        now=datetime.fromisoformat(attempt["lease_expires_at"]) - timedelta(seconds=10),
        elapsed=0,
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now

    def advance(seconds):
        clock.now += timedelta(seconds=seconds)
        clock.elapsed += seconds

    clock.advance = advance
    monkeypatch.setattr(heartbeat, "datetime", Clock)
    monkeypatch.setattr(
        execution, "time", SimpleNamespace(monotonic=lambda: clock.elapsed)
    )
    return clock


@pytest.fixture
def slow_computation(monkeypatch, clock):
    import execution

    original = execution.count_prime_batches
    processed = []

    def batches(limit, batch_size):
        for count in original(limit, batch_size):
            clock.advance(4)
            processed.append(count)
            yield count

    monkeypatch.setattr(execution, "count_prime_batches", batches)
    return processed
