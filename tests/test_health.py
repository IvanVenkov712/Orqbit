import socket

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


def assert_live(client):
    for path in ("/health", "/health/live"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def assert_not_ready(client):
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"
    assert_live(client)


def test_healthy_database_is_ready(client):
    assert_live(client)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["cache-control"] == "no-store"


def test_unreachable_database_is_not_ready_but_api_is_live(
    client, database, monkeypatch
):
    import health

    # Reserve a local port without listening, so connection refusal is real and
    # another process cannot race to claim the port during this test.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        url = database.url.set(host="127.0.0.1", port=unavailable.getsockname()[1])
        engine = create_engine(
            url, poolclass=NullPool, connect_args={"connect_timeout": 1}
        )
        try:
            with monkeypatch.context() as patch:
                patch.setattr(health, "readiness_engine", engine)
                assert_not_ready(client)
        finally:
            engine.dispose()

    # A failed check must not cache the failure or poison subsequent requests.
    assert client.get("/health/ready").status_code == 200


@pytest.mark.parametrize(
    ("break_sql", "restore_sql"),
    [
        (
            "ALTER TABLE alembic_version RENAME TO saved_alembic_version",
            "ALTER TABLE saved_alembic_version RENAME TO alembic_version",
        ),
        (
            "DELETE FROM alembic_version",
            "INSERT INTO alembic_version (version_num) VALUES (:revision)",
        ),
        (
            "UPDATE alembic_version SET version_num = 'older_revision'",
            "UPDATE alembic_version SET version_num = :revision",
        ),
        (
            "ALTER TABLE jobs RENAME TO saved_jobs",
            "ALTER TABLE saved_jobs RENAME TO jobs",
        ),
        (
            "ALTER TABLE jobs RENAME COLUMN created_at TO saved_created_at",
            "ALTER TABLE jobs RENAME COLUMN saved_created_at TO created_at",
        ),
    ],
    ids=[
        "no-version-table",
        "unmigrated",
        "outdated",
        "no-jobs-table",
        "missing-column",
    ],
)
def test_missing_or_outdated_schema_is_not_ready(
    client, database, break_sql, restore_sql
):
    with database.begin() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        connection.execute(text(break_sql))
    try:
        assert_not_ready(client)
    finally:
        with database.begin() as connection:
            connection.execute(text(restore_sql), {"revision": revision})

    assert client.get("/health/ready").status_code == 200


def test_locked_schema_times_out_as_not_ready(client, database):
    with database.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("LOCK TABLE jobs IN ACCESS EXCLUSIVE MODE"))
            assert_not_ready(client)
        finally:
            transaction.rollback()

    assert client.get("/health/ready").status_code == 200
