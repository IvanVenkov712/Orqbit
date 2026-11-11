"""Attempt lease renewal, expiry, ownership, and report contention."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt


@pytest.mark.parametrize("extends", [True, False], ids=["extends", "does-not-shorten"])
def test_heartbeat_renews_lease_without_changing_job(
    client, database, claimed_attempt, monkeypatch, extends
):
    from config import settings

    claim, headers = claimed_attempt
    # Hours leave ample headroom without making the test wait for real expiry.
    monkeypatch.setattr(settings, "lease_extension_seconds", 7200)
    with Session(database) as session:
        now = session.scalar(select(func.clock_timestamp()))
        attempt = session.get(JobAttempt, claim["id"])
        attempt.lease_expires_at = now + timedelta(hours=1 if extends else 3)
        session.commit()
        original_deadline = attempt.lease_expires_at
        original_job = session.execute(select(Job.__table__)).mappings().one()

    with database.connect() as connection:
        before = connection.scalar(select(func.clock_timestamp()))
    response = client.post(f"/workers/{claim['id']}/heartbeat", headers=headers)
    with database.connect() as connection:
        after = connection.scalar(select(func.clock_timestamp()))

    assert response.status_code == 200
    assert set(response.json()) == {"lease_expires_at"}
    renewed = datetime.fromisoformat(response.json()["lease_expires_at"])
    assert renewed.utcoffset() == timedelta(0)
    if extends:
        assert renewed > original_deadline
        assert before + timedelta(hours=2) <= renewed <= after + timedelta(hours=2)
    else:
        assert renewed == original_deadline
    with Session(database) as session:
        attempt = session.get(JobAttempt, claim["id"])
        assert attempt.lease_expires_at == renewed
        assert attempt.status == AttemptStatus.RUNNING
        assert attempt.params == claim["params"]
        assert attempt.result is None
        assert attempt.error is None
        assert session.execute(select(Job.__table__)).mappings().one() == original_job


@pytest.mark.parametrize("endpoint", ["heartbeat", "succeed", "fail"])
def test_expired_lease_rejects_new_reports_without_mutation(
    client, database, claimed_attempt, endpoint
):
    claim, headers = claimed_attempt
    with Session(database) as session:
        now = session.scalar(select(func.clock_timestamp()))
        session.get(JobAttempt, claim["id"]).lease_expires_at = now - timedelta(days=1)
        session.commit()
        original_attempt = (
            session.execute(select(JobAttempt.__table__)).mappings().one()
        )
        original_job = session.execute(select(Job.__table__)).mappings().one()

    payload = (
        {}
        if endpoint == "heartbeat"
        else {"json": {"result" if endpoint == "succeed" else "error": {"value": 3}}}
    )
    response = client.post(
        f"/workers/{claim['id']}/{endpoint}", headers=headers, **payload
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "The lease has expired"}
    with Session(database) as session:
        assert (
            session.execute(select(JobAttempt.__table__)).mappings().one()
            == original_attempt
        )
        assert session.execute(select(Job.__table__)).mappings().one() == original_job


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("missing", 404),
        ("other-worker", 404),
        ("no-key", 401),
        ("SUCCEEDED", 400),
        ("FAILED", 400),
        ("LOST", 400),
    ],
)
def test_heartbeat_requires_owner_and_running_attempt(
    client, database, claimed_attempt, worker_factory, target, expected
):
    claim, headers = claimed_attempt
    target_id = claim["id"]
    if target == "missing":
        target_id = 0
    elif target == "other-worker":
        _, headers = worker_factory()
    elif target == "no-key":
        headers = {}
    else:
        with Session(database) as session:
            attempt = session.get(JobAttempt, claim["id"])
            attempt.status = AttemptStatus(target)
            attempt.job.status = (
                JobStatus.FAILED if target == "LOST" else JobStatus(target)
            )
            session.commit()

    with Session(database) as session:
        original = session.execute(select(JobAttempt.__table__)).mappings().one()
    response = client.post(f"/workers/{target_id}/heartbeat", headers=headers)
    assert response.status_code == expected
    if expected == 404:
        assert response.json() == {"detail": "Attempt not found"}
    elif expected == 400:
        assert response.json() == {"detail": "The attempt is not running"}
    with Session(database) as session:
        assert (
            session.execute(select(JobAttempt.__table__)).mappings().one() == original
        )


@pytest.mark.parametrize("endpoint", ["succeed", "fail"])
@pytest.mark.parametrize("heartbeat_first", [True, False])
def test_concurrent_heartbeat_and_outcome_serialize_on_attempt(
    client, database, claimed_attempt, monkeypatch, endpoint, heartbeat_first
):
    from config import settings
    from database import engine as api_engine
    from main import app

    claim, headers = claimed_attempt
    monkeypatch.setattr(settings, "lease_extension_seconds", 7200)
    with Session(database) as session:
        now = session.scalar(select(func.clock_timestamp()))
        session.get(JobAttempt, claim["id"]).lease_expires_at = now + timedelta(hours=1)
        session.commit()
        original_deadline = session.get(JobAttempt, claim["id"]).lease_expires_at

    locked, release, waiting = Event(), Event(), Event()
    first_pid, waiting_pid = [], []

    def hold_first_update(session, flush_context):
        if not locked.is_set() and any(
            isinstance(record, JobAttempt) and record.id == claim["id"]
            for record in session.dirty
        ):
            first_pid.append(
                session.connection().connection.driver_connection.info.backend_pid
            )
            locked.set()
            assert release.wait(timeout=20), "First update was never released"

    def observe_waiter(connection, cursor, statement, parameters, context, executemany):
        if (
            locked.is_set()
            and "FROM job_attempts" in statement
            and "FOR UPDATE" in statement
        ):
            waiting_pid.append(connection.connection.driver_connection.info.backend_pid)
            waiting.set()

    field = "result" if endpoint == "succeed" else "error"
    requests = {"heartbeat": {}, endpoint: {"json": {field: {"value": 3}}}}
    first_endpoint, second_endpoint = (
        ("heartbeat", endpoint) if heartbeat_first else (endpoint, "heartbeat")
    )
    with TestClient(app) as other_client, ThreadPoolExecutor(max_workers=2) as executor:
        event.listen(Session, "after_flush", hold_first_update)
        event.listen(api_engine, "before_cursor_execute", observe_waiter)
        try:
            first_future = executor.submit(
                client.post,
                f"/workers/{claim['id']}/{first_endpoint}",
                headers=headers,
                **requests[first_endpoint],
            )
            try:
                assert locked.wait(timeout=10), "First update never reached PostgreSQL"
                second_future = executor.submit(
                    other_client.post,
                    f"/workers/{claim['id']}/{second_endpoint}",
                    headers=headers,
                    **requests[second_endpoint],
                )
                assert waiting.wait(timeout=10), (
                    "Second request never attempted its lock"
                )
                # Verify actual server-side blocking before releasing the first request.
                with database.connect() as connection:
                    deadline = monotonic() + 10
                    while monotonic() < deadline:
                        blockers = connection.scalar(
                            select(func.pg_blocking_pids(waiting_pid[0]))
                        )
                        if first_pid[0] in blockers:
                            break
                    else:
                        pytest.fail(
                            "Second request did not wait for the first attempt lock"
                        )
                assert not second_future.done()
            finally:
                release.set()
            first = first_future.result(timeout=10)
            second = second_future.result(timeout=10)
        finally:
            release.set()
            executor.shutdown(wait=True)
            event.remove(Session, "after_flush", hold_first_update)
            event.remove(api_engine, "before_cursor_execute", observe_waiter)

    assert first.status_code == 200
    assert second.status_code == (200 if heartbeat_first else 400)
    if not heartbeat_first:
        assert second.json() == {"detail": "The attempt is not running"}
    with Session(database) as session:
        attempt = session.get(JobAttempt, claim["id"])
        status = "SUCCEEDED" if endpoint == "succeed" else "FAILED"
        assert attempt.status == AttemptStatus(status)
        assert attempt.job.status == JobStatus(status)
        assert getattr(attempt, field) == getattr(attempt.job, field) == {"value": 3}
        if heartbeat_first:
            assert attempt.lease_expires_at > original_deadline
            assert attempt.lease_expires_at == datetime.fromisoformat(
                first.json()["lease_expires_at"]
            )
        else:
            assert attempt.lease_expires_at == original_deadline


@pytest.mark.parametrize("endpoint", ["heartbeat", "succeed", "fail"])
def test_waiting_report_rechecks_expiry_after_acquiring_attempt_lock(
    client, database, claimed_attempt, endpoint
):
    from database import engine as api_engine
    from main import app

    claim, headers = claimed_attempt
    waiting = Event()
    waiting_pid = []

    def observe_waiter(connection, cursor, statement, parameters, context, executemany):
        if "FROM job_attempts" in statement and "FOR UPDATE" in statement:
            waiting_pid.append(connection.connection.driver_connection.info.backend_pid)
            waiting.set()

    payload = (
        {}
        if endpoint == "heartbeat"
        else {"json": {"result" if endpoint == "succeed" else "error": {"value": 3}}}
    )
    with (
        Session(database) as owner,
        TestClient(app) as other_client,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        attempt = owner.scalar(
            select(JobAttempt).where(JobAttempt.id == claim["id"]).with_for_update()
        )
        owner_pid = owner.connection().connection.driver_connection.info.backend_pid
        event.listen(api_engine, "before_cursor_execute", observe_waiter)
        try:
            future = executor.submit(
                other_client.post,
                f"/workers/{claim['id']}/{endpoint}",
                headers=headers,
                **payload,
            )
            try:
                assert waiting.wait(timeout=10), "Request never attempted its lock"
                with database.connect() as connection:
                    deadline = monotonic() + 10
                    while monotonic() < deadline:
                        blockers = connection.scalar(
                            select(func.pg_blocking_pids(waiting_pid[0]))
                        )
                        if owner_pid in blockers:
                            break
                    else:
                        pytest.fail("Request did not wait for the held attempt lock")

                # This instant is later than the waiting request's transaction start.
                # Using transaction_timestamp()/now() after the lock would be stale.
                expired_deadline = owner.scalar(select(func.clock_timestamp()))
                attempt.lease_expires_at = expired_deadline
                owner.commit()
                response = future.result(timeout=10)
            finally:
                owner.rollback()
        finally:
            owner.rollback()
            executor.shutdown(wait=True)
            event.remove(api_engine, "before_cursor_execute", observe_waiter)

    assert response.status_code == 400
    assert response.json() == {"detail": "The lease has expired"}
    with Session(database) as session:
        attempt = session.get(JobAttempt, claim["id"])
        assert attempt.lease_expires_at == expired_deadline
        assert attempt.status == AttemptStatus.RUNNING
        assert attempt.job.status == JobStatus.RUNNING
        assert attempt.result is None and attempt.job.result is None
        assert attempt.error is None and attempt.job.error is None
