"""Bounded PostgreSQL operations and safe HTTP responses after storage failures."""

import socket
from datetime import timedelta

import pytest
from psycopg import OperationalError as PsycopgOperationalError
from psycopg.errors import (
    AdminShutdown,
    CannotConnectNow,
    ConnectionFailure,
    CrashShutdown,
    DeadlockDetected,
    DiskFull,
    ForeignKeyViolation,
    InvalidPassword,
    InvalidTextRepresentation,
    LockNotAvailable,
    QueryCanceled,
    SerializationFailure,
    TooManyConnections,
    UndefinedTable,
)
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import (
    DataError,
    DBAPIError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
)
from sqlalchemy.exc import TimeoutError as DatabasePoolTimeout
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt


def assert_unavailable(response):
    assert response.status_code == 503
    assert response.json() == {"detail": "Database temporarily unavailable"}
    assert response.headers["retry-after"] == "1"
    assert response.headers["cache-control"] == "no-store"


@pytest.fixture
def limited_api(database, monkeypatch):
    import database as api_database
    from config import settings

    monkeypatch.setattr(settings, "database_statement_timeout_ms", 250)
    monkeypatch.setattr(settings, "database_lock_timeout_ms", 100)
    engine = create_engine(database.url, pool_size=1, max_overflow=0, pool_timeout=0.1)
    event.listen(engine, "connect", api_database.set_database_timeouts)
    monkeypatch.setitem(api_database.SessionLocal.kw, "bind", engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "name", ["database_statement_timeout_ms", "database_lock_timeout_ms"]
)
@pytest.mark.parametrize("value", [0, -1, 2147483648])
def test_database_timeouts_reject_disabled_or_invalid_values(name, value):
    from config import Settings, settings

    values = {**settings.model_dump(), name: value}
    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None, **values)
    assert raised.value.errors()[0]["loc"] == (name,)


def test_application_timeouts_survive_rollback_and_reconnection(database):
    import database as api_database
    from config import settings

    with database.connect() as connection:
        expected_schema = connection.scalar(text("SELECT current_schema()"))
    for _ in range(2):
        with api_database.engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == expected_schema
            connection.rollback()
            for name, expected in (
                ("statement_timeout", settings.database_statement_timeout_ms),
                ("lock_timeout", settings.database_lock_timeout_ms),
            ):
                value = connection.scalar(
                    text("SELECT current_setting(:name)::interval"), {"name": name}
                )
                assert value == timedelta(milliseconds=expected)
            connection.execute(text("SET LOCAL statement_timeout = '1ms'"))
            connection.rollback()
            assert connection.scalar(
                text("SELECT current_setting('statement_timeout')::interval")
            ) == timedelta(milliseconds=settings.database_statement_timeout_ms)
        # Force a fresh physical connection, not just another pool checkout.
        api_database.engine.dispose()


@pytest.mark.parametrize(
    "error, expected",
    [
        *[
            (OperationalError("private SQL", {}, error("private credentials")), 503)
            for error in (
                PsycopgOperationalError,
                ConnectionFailure,
                SerializationFailure,
                DeadlockDetected,
                TooManyConnections,
                DiskFull,
                LockNotAvailable,
                QueryCanceled,
                AdminShutdown,
                CrashShutdown,
                CannotConnectNow,
            )
        ],
        (
            DBAPIError(
                "private SQL",
                {},
                Exception("private credentials"),
                connection_invalidated=True,
            ),
            503,
        ),
        (DatabasePoolTimeout("private connection details"), 503),
        (
            OperationalError("private SQL", {}, InvalidPassword("private credentials")),
            500,
        ),
        (ProgrammingError("private SQL", {}, UndefinedTable("private table")), 500),
        (IntegrityError("private SQL", {}, ForeignKeyViolation("private values")), 500),
        (DataError("private SQL", {}, InvalidTextRepresentation("private input")), 422),
    ],
)
def test_database_errors_have_safe_distinct_http_responses(
    client, user_headers, monkeypatch, error, expected
):
    from database import get_session
    from main import app

    def unavailable_session():
        raise error

    with monkeypatch.context() as patch:
        patch.setitem(app.dependency_overrides, get_session, unavailable_session)
        response = client.get("/jobs", headers=user_headers)
    if expected == 503:
        assert_unavailable(response)
    else:
        assert response.status_code == expected
        assert response.json() == {
            "detail": (
                "Database operation failed"
                if expected == 500
                else "Input contains a value PostgreSQL cannot store"
            )
        }
        assert "retry-after" not in response.headers
    assert client.get("/jobs", headers=user_headers).status_code == 200


def test_connection_refusal_returns_503_then_requests_recover(
    client, database, user_headers, monkeypatch
):
    import database as api_database

    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        engine = create_engine(
            database.url.set(host="127.0.0.1", port=unavailable.getsockname()[1]),
            poolclass=NullPool,
            connect_args={"connect_timeout": 1},
        )
        try:
            with monkeypatch.context() as patch:
                patch.setitem(api_database.SessionLocal.kw, "bind", engine)
                assert_unavailable(client.get("/jobs", headers=user_headers))
                assert client.get("/health/live").status_code == 200
        finally:
            engine.dispose()
    assert client.get("/jobs", headers=user_headers).status_code == 200


def test_exhausted_pool_returns_503_then_reuses_released_connection(
    client, user_headers, limited_api
):
    with limited_api.connect():
        assert_unavailable(client.get("/jobs", headers=user_headers))
    assert client.get("/jobs", headers=user_headers).status_code == 200


def test_statement_timeout_rolls_back_flushed_claim_and_reuses_connection(
    client, database, claim_worker, job_factory, limited_api
):
    _, headers = claim_worker
    with Session(database) as session:
        job = job_factory()
        session.add(job)
        session.commit()
        job_id = job.id
    with limited_api.connect() as connection:
        backend_pid = connection.scalar(select(func.pg_backend_pid()))

    def time_out_after_writes(session, flush_context):
        if any(isinstance(record, JobAttempt) for record in session.new):
            try:
                session.execute(text("SELECT pg_sleep(10)"))
            except OperationalError as error:
                assert error.orig.sqlstate == "57014"
                raise

    event.listen(Session, "after_flush", time_out_after_writes)
    try:
        assert_unavailable(client.post("/workers/claim", headers=headers))
    finally:
        event.remove(Session, "after_flush", time_out_after_writes)
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.PENDING
        assert job.attempts_count == 0
        assert session.scalars(select(JobAttempt)).all() == []
    with limited_api.connect() as connection:
        assert connection.scalar(select(func.pg_backend_pid())) == backend_pid
    retried = client.post("/workers/claim", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["job_id"] == job_id
    assert retried.json()["attempt_number"] == 1


def test_lock_timeout_rolls_back_outcome_and_releases_attempt_lock(
    client, database, claimed_attempt, limited_api
):
    claim, headers = claimed_attempt
    sqlstates = []

    def record_error(context):
        sqlstates.append(context.original_exception.sqlstate)

    with Session(database) as blocker:
        blocker.scalar(select(Job).where(Job.id == claim["job_id"]).with_for_update())
        event.listen(limited_api, "handle_error", record_error)
        try:
            response = client.post(
                f"/workers/{claim['id']}/succeed",
                headers=headers,
                json={"result": {"ok": True}},
            )
        finally:
            event.remove(limited_api, "handle_error", record_error)
        assert_unavailable(response)
        assert sqlstates == ["55P03"]
        with Session(database) as session:
            attempt = session.scalar(
                select(JobAttempt)
                .where(JobAttempt.id == claim["id"])
                .with_for_update(nowait=True)
            )
            assert attempt.status == AttemptStatus.RUNNING
            assert attempt.result is None
            assert attempt.job.status == JobStatus.RUNNING
            assert attempt.job.result is None
    retried = client.post(
        f"/workers/{claim['id']}/succeed",
        headers=headers,
        json={"result": {"ok": True}},
    )
    assert retried.status_code == 200
    with Session(database) as session:
        assert session.get(Job, claim["job_id"]).status == JobStatus.SUCCEEDED


@pytest.mark.parametrize("timeout", ["lock", "statement"])
def test_recovery_rolls_back_timeouts_and_continues_with_a_fresh_session(
    database, claimed_attempt, limited_api, monkeypatch, timeout
):
    import recovery

    claim, _ = claimed_attempt
    with Session(database) as session:
        attempt = session.get(JobAttempt, claim["id"])
        attempt.lease_expires_at = session.scalar(
            select(func.clock_timestamp())
        ) - timedelta(days=1)
        attempt.job.max_attempts = 1
        session.commit()
    sessions = []
    pauses = []

    def session_factory():
        session = Session(limited_api)
        sessions.append(session)
        return session

    def time_out_before_job_update(
        connection, cursor, statement, parameters, context, many
    ):
        if len(sessions) == 1 and statement.startswith("UPDATE jobs SET"):
            connection.exec_driver_sql("SELECT pg_sleep(10)")

    with Session(database) as blocker:
        if timeout == "lock":
            blocker.scalar(
                select(JobAttempt).where(JobAttempt.id == claim["id"]).with_for_update()
            )

        def pause(seconds):
            pauses.append(seconds)
            assert not sessions[-1].in_transaction()
            with Session(database) as session:
                attempt = session.get(JobAttempt, claim["id"])
                if len(pauses) == 1:
                    assert attempt.status == AttemptStatus.RUNNING
                    assert attempt.job.status == JobStatus.RUNNING
                    blocker.rollback()
                    return
                assert attempt.status == AttemptStatus.LOST
                assert attempt.job.status == JobStatus.FAILED
            raise KeyboardInterrupt

        monkeypatch.setattr(recovery, "SessionLocal", session_factory)
        monkeypatch.setattr(recovery, "sleep", pause)
        if timeout == "statement":
            event.listen(
                limited_api, "before_cursor_execute", time_out_before_job_update
            )
        try:
            with pytest.raises(KeyboardInterrupt):
                recovery.main()
        finally:
            if timeout == "statement":
                event.remove(
                    limited_api, "before_cursor_execute", time_out_before_job_update
                )
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert pauses == [recovery.settings.recovery_interval_seconds] * 2
