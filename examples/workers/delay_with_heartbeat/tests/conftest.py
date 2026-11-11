import pytest

from settings import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        api_key="worker-key",
        api_url="http://localhost:8000",
        execution_delay=12,
    )


@pytest.fixture
def attempt():
    return {
        "id": 17,
        "job_id": 42,
        "job_type": "delay_with_heartbeat",
        "params": {},
        "lease_expires_at": "2030-01-01T00:00:10Z",
    }


@pytest.fixture
def clock(monkeypatch):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    import heartbeat

    clock = SimpleNamespace(now=datetime(2030, 1, 1, tzinfo=UTC), elapsed=0, sleeps=[])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now

    def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.elapsed += seconds
        clock.now += timedelta(seconds=seconds)

    monkeypatch.setattr(heartbeat, "datetime", Clock)
    monkeypatch.setattr(
        heartbeat,
        "time",
        SimpleNamespace(
            sleep=sleep,
            monotonic=lambda: clock.elapsed,
        ),
    )
    return clock
