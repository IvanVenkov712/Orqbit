import pytest

from settings import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, api_key="worker-key", api_url="http://localhost:8000"
    )
