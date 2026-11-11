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
        "HEARTBEAT_INTERVAL",
        "BATCH_SIZE",
    ):
        monkeypatch.delenv(name, raising=False)
    script = tmp_path / "settings.py"
    script.write_text(
        Path(configuration.__file__).read_text(encoding="utf-8"), encoding="utf-8"
    )
    script.with_name(".env").write_text(
        "API_KEY=file-key\nAPI_URL=http://localhost:8123\n"
        "POLL_INTERVAL=3\nREQUEST_TIMEOUT=5\nBATCH_SIZE=7\nHEARTBEAT_INTERVAL=4\n",
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
    assert settings.batch_size == 7
    assert settings.heartbeat_interval == 4
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("batch_size", 0),
        ("batch_size", 10001),
        ("heartbeat_interval", 0),
        ("heartbeat_interval", float("inf")),
    ],
)
def test_batch_and_heartbeat_settings_reject_invalid_values(field, value):
    with pytest.raises(ValidationError):
        configuration.Settings(
            _env_file=None,
            api_key="key",
            api_url="http://localhost:8000",
            **{field: value},
        )
