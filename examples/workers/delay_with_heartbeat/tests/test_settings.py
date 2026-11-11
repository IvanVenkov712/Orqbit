import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

import settings as configuration


def test_adjacent_env_and_environment_override(tmp_path, monkeypatch):
    for name in (
        "API_KEY",
        "API_URL",
        "POLL_INTERVAL",
        "REQUEST_TIMEOUT",
        "EXECUTION_DELAY",
        "HEARTBEAT_INTERVAL",
    ):
        monkeypatch.delenv(name, raising=False)
    script = tmp_path / "settings.py"
    script.write_text(
        Path(configuration.__file__).read_text(encoding="utf-8"), encoding="utf-8"
    )
    script.with_name(".env").write_text(
        "API_KEY=file-key\nAPI_URL=http://localhost:8123\n"
        "POLL_INTERVAL=3\nREQUEST_TIMEOUT=5\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path.parent)
    spec = importlib.util.spec_from_file_location("relocated_settings", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = module.Settings()

    assert settings.api_key.get_secret_value() == "file-key"
    assert str(settings.api_url) == "http://localhost:8123/"
    assert settings.poll_interval == 3
    assert settings.request_timeout == 5
    monkeypatch.setenv("API_KEY", "environment-key")
    assert module.Settings().api_key.get_secret_value() == "environment-key"


@pytest.mark.parametrize("value", [0, -1, float("inf")])
def test_request_timeout_must_be_positive_and_finite(value):
    with pytest.raises(ValidationError):
        configuration.Settings(
            _env_file=None,
            api_key="key",
            api_url="http://localhost:8000",
            request_timeout=value,
        )


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_execution_delay_must_be_nonnegative_and_finite(value):
    with pytest.raises(ValidationError):
        configuration.Settings(
            _env_file=None,
            api_key="key",
            api_url="http://localhost:8000",
            execution_delay=value,
        )


@pytest.mark.parametrize("value", [0, -1, float("inf")])
def test_heartbeat_interval_must_be_positive_and_finite(value):
    with pytest.raises(ValidationError):
        configuration.Settings(
            _env_file=None,
            api_key="key",
            api_url="http://localhost:8000",
            heartbeat_interval=value,
        )
