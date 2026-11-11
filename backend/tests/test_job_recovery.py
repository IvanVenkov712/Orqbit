"""Expired-attempt recovery, rollback, and concurrent reports."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt


def test_recovery_handles_empty_queue(database):
    from services.job_execution import recover_expired_attempts

    with Session(database) as session:
        recover_expired_attempts(session)
    with Session(database) as session:
        assert session.scalars(select(Job)).all() == []
        assert session.scalars(select(JobAttempt)).all() == []


def test_recovery_preserves_unexpired_and_terminal_attempts(database, claim_worker):
    from services.job_execution import recover_expired_attempts

    worker, _ = claim_worker
    models = (Job, JobAttempt)
    expired_job_ids, expired_attempt_ids = set(), set()
    with Session(database) as session:
        now = session.scalar(select(func.clock_timestamp()))
        for index, status in enumerate(
            [
                AttemptStatus.RUNNING,
                AttemptStatus.RUNNING,
                AttemptStatus.RUNNING,
                AttemptStatus.SUCCEEDED,
                AttemptStatus.FAILED,
                AttemptStatus.LOST,
            ]
        ):
            job = Job(
                job_type="example",
                params={"index": index},
                user_id=worker.user_id,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
                status=JobStatus.FAILED
                if status == AttemptStatus.LOST
                else JobStatus(status.value),
                result={"value": index} if status == AttemptStatus.SUCCEEDED else None,
                error={"message": "failed"} if status == AttemptStatus.FAILED else None,
            )
            attempt = JobAttempt(
                job=job,
                worker_id=worker.id,
                attempt_number=1,
                params=job.params,
                status=status,
                result=job.result,
                error=job.error,
                lease_expires_at=now + timedelta(days=1 if index == 2 else -1),
            )
            session.add(attempt)
            session.flush()
            if index < 2:
                expired_job_ids.add(job.id)
                expired_attempt_ids.add(attempt.id)
            if index == 2:
                # An older lost attempt must not fail a currently leased job.
                attempt.attempt_number = 2
                session.add(
                    JobAttempt(
                        job=job,
                        worker_id=worker.id,
                        attempt_number=1,
                        params=job.params,
                        status=AttemptStatus.LOST,
                        lease_expires_at=now - timedelta(days=2),
                    )
                )
        session.add(
            Job(
                job_type="example",
                params={},
                user_id=worker.user_id,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
            )
        )
        session.commit()
        before = {
            model: {
                row["id"]: dict(row)
                for row in session.execute(select(model.__table__)).mappings()
            }
            for model in models
        }

    with Session(database) as session:
        recover_expired_attempts(session)

    with Session(database) as session:
        after = {
            model: {
                row["id"]: dict(row)
                for row in session.execute(select(model.__table__)).mappings()
            }
            for model in models
        }
        for model, changed_ids, status in (
            (Job, expired_job_ids, JobStatus.FAILED),
            (JobAttempt, expired_attempt_ids, AttemptStatus.LOST),
        ):
            assert after[model].keys() == before[model].keys()
            for record_id, record in after[model].items():
                expected = before[model][record_id].copy()
                if record_id in changed_ids:
                    assert record["updated_at"] >= expected["updated_at"]
                    expected.update(status=status, updated_at=record["updated_at"])
                assert record == expected
        recover_expired_attempts(session)

    # A repeated scan must not rewrite even the timestamps of recovered records.
    with Session(database) as session:
        for model in models:
            assert {
                row["id"]: dict(row)
                for row in session.execute(select(model.__table__)).mappings()
            } == after[model]


def test_recovery_failure_rolls_back_attempt_and_job(database, claimed_attempt):
    from services.job_execution import recover_expired_attempts

    claim, _ = claimed_attempt
    with Session(database) as session:
        now = session.scalar(select(func.clock_timestamp()))
        session.get(JobAttempt, claim["id"]).lease_expires_at = now - timedelta(days=1)
        session.commit()
        before_attempt = session.execute(select(JobAttempt.__table__)).mappings().one()
        before_job = session.execute(select(Job.__table__)).mappings().one()

    def reject_job_update(
        connection, cursor, statement, parameters, context, executemany
    ):
        if statement.startswith("UPDATE jobs SET"):
            raise RuntimeError("Simulated recovery failure after attempt update")

    event.listen(database, "before_cursor_execute", reject_job_update)
    try:
        with pytest.raises(RuntimeError, match="Simulated recovery failure"):
            with Session(database) as session:
                recover_expired_attempts(session)
    finally:
        event.remove(database, "before_cursor_execute", reject_job_update)

    with Session(database) as session:
        assert session.execute(select(JobAttempt.__table__)).mappings().one() == (
            before_attempt
        )
        assert session.execute(select(Job.__table__)).mappings().one() == before_job


@pytest.mark.parametrize(
    ("other_operation", "recovery_first"),
    [
        ("heartbeat", True),
        ("heartbeat", False),
        ("succeed", True),
        ("succeed", False),
        ("fail", True),
        ("fail", False),
        ("recovery", True),
    ],
)
def test_recovery_serializes_with_reports_and_other_recovery(
    client, database, claimed_attempt, monkeypatch, other_operation, recovery_first
):
    from config import settings
    from database import engine as api_engine
    from services import job_execution

    claim, headers = claimed_attempt
    monkeypatch.setattr(settings, "lease_extension_seconds", 14400)
    with Session(database) as session:
        now = session.scalar(select(func.clock_timestamp()))
        original_deadline = now + timedelta(hours=-1 if recovery_first else 1)
        recovery_cutoff = now + timedelta(hours=2)
        session.get(JobAttempt, claim["id"]).lease_expires_at = original_deadline
        session.commit()

    original_get_db_now = job_execution.get_db_now

    def get_db_now(session):
        # Simulate recovery starting after the original deadline while a report
        # admitted before expiry still holds its transaction open. Heartbeats
        # extend beyond this cutoff, so PostgreSQL must recheck their new lease.
        if not recovery_first and session.info.get("recovery"):
            return recovery_cutoff
        return original_get_db_now(session)

    monkeypatch.setattr(job_execution, "get_db_now", get_db_now)
    locked, release, waiting = Event(), Event(), Event()
    first_pid, waiting_pid = [], []

    def hold_first_update(
        connection, cursor, statement, parameters, context, executemany
    ):
        if not locked.is_set() and statement.startswith("UPDATE job_attempts SET"):
            first_pid.append(connection.connection.driver_connection.info.backend_pid)
            locked.set()
            assert release.wait(timeout=20), "First update was never released"

    def observe_waiter(connection, cursor, statement, parameters, context, executemany):
        if locked.is_set() and (
            statement.startswith("UPDATE job_attempts SET")
            or ("FROM job_attempts" in statement and "FOR UPDATE" in statement)
        ):
            waiting_pid.append(connection.connection.driver_connection.info.backend_pid)
            waiting.set()

    def recover():
        with Session(database, info={"recovery": True}) as session:
            job_execution.recover_expired_attempts(session)

    field = "result" if other_operation == "succeed" else "error"

    def report():
        payload = (
            {} if other_operation == "heartbeat" else {"json": {field: {"value": 3}}}
        )
        return client.post(
            f"/workers/{claim['id']}/{other_operation}", headers=headers, **payload
        )

    other = recover if other_operation == "recovery" else report
    first_call, second_call = (recover, other) if recovery_first else (other, recover)
    with ThreadPoolExecutor(max_workers=2) as executor:
        for engine in (database, api_engine):
            event.listen(engine, "after_cursor_execute", hold_first_update)
            event.listen(engine, "before_cursor_execute", observe_waiter)
        try:
            first_future = executor.submit(first_call)
            try:
                assert locked.wait(timeout=10), "First update never reached PostgreSQL"
                second_future = executor.submit(second_call)
                assert waiting.wait(timeout=10), (
                    "Second operation never attempted its lock"
                )
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
                            "Second operation did not wait for the attempt lock"
                        )
                assert not second_future.done()
            finally:
                release.set()
            first = first_future.result(timeout=10)
            second = second_future.result(timeout=10)
        finally:
            release.set()
            executor.shutdown(wait=True)
            for engine in (database, api_engine):
                event.remove(engine, "after_cursor_execute", hold_first_update)
                event.remove(engine, "before_cursor_execute", observe_waiter)

    if recovery_first:
        assert first is None
        if other_operation == "recovery":
            assert second is None
        else:
            assert second.status_code == (
                400 if other_operation == "heartbeat" else 409
            )
            assert second.json() == {
                "detail": (
                    "The attempt is not running"
                    if other_operation == "heartbeat"
                    else "Conflicting outcome report"
                )
            }
    else:
        assert first.status_code == 200
        assert second is None

    with Session(database) as session:
        attempt = session.get(JobAttempt, claim["id"])
        if recovery_first:
            assert attempt.status == AttemptStatus.LOST
            assert attempt.job.status == JobStatus.FAILED
        elif other_operation == "heartbeat":
            assert attempt.status == AttemptStatus.RUNNING
            assert attempt.job.status == JobStatus.RUNNING
            assert attempt.lease_expires_at > recovery_cutoff
            assert attempt.lease_expires_at == datetime.fromisoformat(
                first.json()["lease_expires_at"]
            )
        else:
            status = "SUCCEEDED" if other_operation == "succeed" else "FAILED"
            assert attempt.status == AttemptStatus(status)
            assert attempt.job.status == JobStatus(status)
            assert (
                getattr(attempt, field) == getattr(attempt.job, field) == {"value": 3}
            )
        if recovery_first or other_operation != "heartbeat":
            assert attempt.lease_expires_at == original_deadline
        if recovery_first or other_operation == "heartbeat":
            assert attempt.result is None and attempt.job.result is None
            assert attempt.error is None and attempt.job.error is None
        assert attempt.params == claim["params"]
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 1
