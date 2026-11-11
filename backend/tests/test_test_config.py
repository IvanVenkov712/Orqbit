import os
import shutil
import subprocess
import sys
from textwrap import dedent

import conftest
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text


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
def test_database_configuration_rejects_unsafe_urls(monkeypatch, value):
    monkeypatch.setenv("TEST_DATABASE_URL", value)

    with pytest.raises(pytest.UsageError, match="TEST_DATABASE_URL"):
        conftest._test_database_url()


def test_configuration_rejects_application_imported_before_isolation():
    import config  # noqa: F401 - reproduce configuration cached before pytest setup.

    with pytest.raises(
        pytest.UsageError, match="imported before test database isolation"
    ):
        conftest.pytest_configure(None)


@pytest.mark.parametrize("source", ["environment", "file"])
def test_collection_isolates_early_application_imports(tmp_path, source):
    suite = tmp_path / "tests"
    suite.mkdir()
    shutil.copyfile(conftest.__file__, suite / "conftest.py")
    (suite / "test_early_import.py").write_text(
        dedent("""\
        import os
        import re

        # Exercise the import that originally loaded application settings early.
        import models.job_attempts
        import database
        import health
        from config import settings
        from main import app
        from sqlalchemy.engine import make_url

        url = make_url(os.environ["DATABASE_URL"])
        assert url.database == "collection_test"
        assert re.fullmatch(
            r"-csearch_path=test_[0-9a-f]{32} -ctimezone=UTC", url.query["options"]
        )
        assert make_url(str(settings.database_url)) == url
        assert database.engine.url == url
        assert database.readiness_engine.url == url
        assert database.SessionLocal.kw["bind"].url == url
        assert health.readiness_engine.url == url
        assert settings.secret_key == "0" * 64
        assert settings.lease_extension_seconds == 60
        assert settings.recovery_interval_seconds == 5
        assert settings.recovery_batch_size == 1000
        assert settings.max_unknown_database_errors == 3

        def test_placeholder():
            pass
        """),
        encoding="utf-8",
    )
    # The application's .env must not provide the database or test credentials.
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+psycopg://localhost/application\n"
        "SECRET_KEY=invalid\nLEASE_EXTENSION_SECONDS=invalid\n"
        "RECOVERY_INTERVAL_SECONDS=invalid\n"
        "RECOVERY_BATCH_SIZE=invalid\nMAX_UNKNOWN_DATABASE_ERRORS=invalid\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.pop("TEST_DATABASE_URL", None)
    environment.pop("SECRET_KEY", None)
    environment.pop("LEASE_EXTENSION_SECONDS", None)
    environment.pop("RECOVERY_INTERVAL_SECONDS", None)
    environment.pop("RECOVERY_BATCH_SIZE", None)
    environment.pop("MAX_UNKNOWN_DATABASE_ERRORS", None)
    environment["DATABASE_URL"] = "postgresql+psycopg://localhost/application"
    environment["PYTHONPATH"] = str(conftest.ROOT / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    test_url = "postgresql+psycopg://localhost/collection_test"
    if source == "environment":
        environment["TEST_DATABASE_URL"] = test_url
    else:
        (tmp_path / ".env.test").write_text(
            f"TEST_DATABASE_URL={test_url}\n", encoding="utf-8"
        )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 test collected" in result.stdout


def test_recovery_settings_load_environment(monkeypatch):
    from config import Settings

    monkeypatch.setenv("RECOVERY_BATCH_SIZE", "250")
    monkeypatch.setenv("MAX_UNKNOWN_DATABASE_ERRORS", "4")

    settings = Settings(_env_file=None)
    assert settings.recovery_batch_size == 250
    assert settings.max_unknown_database_errors == 4


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RECOVERY_BATCH_SIZE", "0"),
        ("RECOVERY_BATCH_SIZE", "-1"),
        ("RECOVERY_BATCH_SIZE", "65531"),
        ("MAX_UNKNOWN_DATABASE_ERRORS", "0"),
        ("MAX_UNKNOWN_DATABASE_ERRORS", "-1"),
    ],
)
def test_recovery_settings_reject_invalid_limits(monkeypatch, name, value):
    from config import Settings

    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None)
    assert raised.value.errors()[0]["loc"] == (name.lower(),)


@pytest.mark.parametrize(
    "target", ["settings", "engine", "readiness_engine", "session"]
)
def test_database_fixture_rejects_misdirected_cached_configuration(
    monkeypatch, pytestconfig, target
):
    import database
    from config import settings

    unsafe_url = "postgresql+psycopg://localhost/application"
    unsafe_engine = create_engine(unsafe_url)
    try:
        if target == "settings":
            monkeypatch.setattr(settings, "database_url", unsafe_url)
        elif target == "session":
            monkeypatch.setitem(database.SessionLocal.kw, "bind", unsafe_engine)
        else:
            monkeypatch.setattr(database, target, unsafe_engine)

        def unexpected_database_access(*args, **kwargs):
            pytest.fail("Database setup must stop before creating engines or migrating")

        monkeypatch.setattr(conftest, "create_engine", unexpected_database_access)
        monkeypatch.setattr(conftest.command, "upgrade", unexpected_database_access)
        fixture = conftest.database_engine.__wrapped__(None, pytestconfig)
        with pytest.raises(pytest.UsageError, match="isolated test database URL"):
            next(fixture)
    finally:
        unsafe_engine.dispose()


def test_api_and_migrations_use_the_same_isolated_schema(database_engine, pytestconfig):
    import database

    isolated_url, schema = pytestconfig.stash[conftest.TEST_DATABASE]
    for engine in (database_engine, database.engine, database.readiness_engine):
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == (
                isolated_url.database
            )
            assert connection.scalar(text("SELECT current_schema()")) == schema
            assert connection.scalar(text("SELECT version_num FROM alembic_version"))

    with database.SessionLocal() as session:
        assert session.scalar(text("SELECT current_schema()")) == schema
