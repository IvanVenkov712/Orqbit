from datetime import UTC, datetime, timedelta

import pytest

from settings import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        api_key="worker-key",
        api_url="http://localhost:8000",
    )


@pytest.fixture
def attempt():
    return {
        "id": 17,
        "job_id": 42,
        "job_type": "csv_summary",
        "params": {"csv": "name,amount\nA,10\nB,20\n", "columns": ["amount"]},
        "lease_expires_at": (datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
    }
