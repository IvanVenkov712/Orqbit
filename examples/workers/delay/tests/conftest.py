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
        "job_type": "delay",
        "params": {},
        "lease_expires_at": "2030-01-01T00:00:10Z",
    }
