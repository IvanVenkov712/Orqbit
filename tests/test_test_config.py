import conftest
import pytest


@pytest.mark.parametrize(
    ("file_url", "environment_url", "expected"),
    [
        (None, None, None),
        (
            "postgresql+psycopg://localhost/file_test",
            None,
            "postgresql+psycopg://localhost/file_test",
        ),
        (
            None,
            "postgresql+psycopg://localhost/ci_test",
            "postgresql+psycopg://localhost/ci_test",
        ),
        (
            "postgresql+psycopg://localhost/file_test",
            "postgresql+psycopg://localhost/ci_test",
            "postgresql+psycopg://localhost/ci_test",
        ),
    ],
)
def test_database_settings_load_file_with_environment_precedence(
    tmp_path, monkeypatch, file_url, environment_url, expected
):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/application")
    env_file = tmp_path / ".env.test"
    if file_url is not None:
        env_file.write_text(f"TEST_DATABASE_URL={file_url}\n", encoding="utf-8")
    if environment_url is not None:
        monkeypatch.setenv("TEST_DATABASE_URL", environment_url)

    settings = conftest.TestDatabaseSettings(_env_file=env_file)

    assert settings.database_url == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-database-url",
        "sqlite:///orqbit_test",
        "postgresql+psycopg://localhost/orqbit",
    ],
)
def test_database_fixture_rejects_unsafe_configuration(monkeypatch, value):
    monkeypatch.setenv("TEST_DATABASE_URL", value)
    fixture = conftest.database_engine.__wrapped__(None)

    with pytest.raises(pytest.UsageError, match="TEST_DATABASE_URL"):
        next(fixture)
