"""Owned outcome reports, terminal replays, and rejected updates."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt


@pytest.mark.parametrize(
    ("endpoint", "field", "status"),
    [("succeed", "result", "SUCCEEDED"), ("fail", "error", "FAILED")],
)
def test_claim_and_report_outcome(
    client, database, user_headers, claim_worker, monkeypatch, endpoint, field, status
):
    import models.job_attempts as attempt_model
    from config import settings

    class SkewedClock:
        @staticmethod
        def now(tz):
            return datetime(2099, 1, 1, tzinfo=tz)

    # Claim deadlines must not depend on the model's local-clock fallback.
    monkeypatch.setattr(attempt_model, "datetime", SkewedClock)

    worker, headers = claim_worker
    response = client.post(
        "/jobs/",
        headers={**user_headers, "Idempotency-Key": "outcome-test"},
        json={"job_type": "example", "params": {}, "permission_policy": "PRIVATE"},
    )
    assert response.status_code == 200
    job_id = response.json()["id"]

    # A known earlier timestamp avoids sleeps and clock-resolution races.
    old_time = datetime(2020, 1, 1, tzinfo=UTC)
    with Session(database) as session:
        job = session.get(Job, job_id)
        job.created_at = old_time
        job.updated_at = old_time
        session.commit()

    with database.connect() as connection:
        before_claim = connection.scalar(select(func.clock_timestamp()))
    response = client.post("/workers/claim", headers=headers)
    with database.connect() as connection:
        after_claim = connection.scalar(select(func.clock_timestamp()))
    assert response.status_code == 200
    attempt_id = response.json()["id"]
    assert response.json()["job_id"] == job_id
    assert response.json()["attempt_number"] == 1
    assert response.json()["params"] == {}
    assert response.json()["status"] == "RUNNING"
    assert set(response.json()) == {
        "id",
        "job_id",
        "job_type",
        "attempt_number",
        "status",
        "params",
        "lease_expires_at",
    }
    initial_deadline = datetime.fromisoformat(response.json()["lease_expires_at"])
    lease_duration = timedelta(seconds=settings.lease_seconds)
    assert initial_deadline.utcoffset() == timedelta(0)
    assert (
        before_claim + lease_duration
        <= initial_deadline
        <= after_claim + lease_duration
    )
    response = client.get(f"/jobs/{job_id}/attempts", headers=user_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    running = response.json()[0]
    assert running["id"] == attempt_id
    assert running["status"] == "RUNNING"
    assert running["result"] is None
    assert running["error"] is None
    assert datetime.fromisoformat(running["lease_expires_at"]) == initial_deadline
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.created_at == old_time
        assert job.updated_at > old_time
        assert job.updated_at.utcoffset() == timedelta(0)
        # Also independently verify the timestamp change on completion/failure.
        job.updated_at = old_time
        session.get(JobAttempt, attempt_id).updated_at = old_time
        session.commit()

    outcome = {"message": "Здравей", "values": [True, None, 3.5, 1e20]}
    response = client.post(
        f"/workers/{attempt_id}/{endpoint}", headers=headers, json={field: outcome}
    )
    assert response.status_code == 200

    response = client.get(f"/jobs/{job_id}", headers=user_headers)
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()[field] == outcome
    other_field = "error" if field == "result" else "result"
    assert response.json()[other_field] is None
    assert response.json()["attempt_ids"] == [attempt_id]
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.status == JobStatus(status)
        assert getattr(job, field) == outcome
        assert job.created_at == old_time
        assert job.updated_at > old_time
        assert job.updated_at.utcoffset() == timedelta(0)
        attempt = session.get(JobAttempt, attempt_id)
        assert attempt.lease_expires_at == initial_deadline
        assert attempt.worker_id == worker.id
        assert attempt.status == AttemptStatus(status)
        assert getattr(attempt, field) == outcome
        assert getattr(attempt, other_field) is None
        assert attempt.updated_at > old_time
        job_updated_at = job.updated_at
        attempt_updated_at = attempt.updated_at

    response = client.get(f"/jobs/{job_id}/attempts", headers=user_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    history = response.json()[0]
    assert set(history) == {
        "id",
        "job_id",
        "job_type",
        "attempt_number",
        "status",
        "params",
        "worker_id",
        "result",
        "error",
        "created_at",
        "updated_at",
        "lease_expires_at",
    }
    assert history["id"] == attempt_id
    assert history["job_id"] == job_id
    assert history["job_type"] == "example"
    assert history["attempt_number"] == 1
    assert history["params"] == {}
    assert history["worker_id"] == worker.id
    assert history["status"] == status
    assert history[field] == outcome
    assert history[other_field] is None
    assert datetime.fromisoformat(history["created_at"]) == attempt.created_at
    assert datetime.fromisoformat(history["updated_at"]) == attempt_updated_at
    assert datetime.fromisoformat(history["lease_expires_at"]) == initial_deadline

    response = client.post(
        f"/workers/{attempt_id}/{endpoint}", headers=headers, json={field: outcome}
    )
    assert response.status_code == 200
    assert response.json() == {"Status": "200 OK"}
    with Session(database) as session:
        job = session.get(Job, job_id)
        attempt = session.get(JobAttempt, attempt_id)
        assert job.updated_at == job_updated_at
        assert attempt.updated_at == attempt_updated_at
        for record in (job, attempt):
            assert getattr(record, field) == outcome
            assert getattr(record, other_field) is None
            assert record.status.value == status


@pytest.mark.parametrize(
    ("endpoint", "field"),
    [("succeed", "result"), ("fail", "error")],
)
@pytest.mark.parametrize(
    "status", [AttemptStatus.SUCCEEDED, AttemptStatus.FAILED, AttemptStatus.LOST]
)
@pytest.mark.parametrize("same_payload", [False, True])
@pytest.mark.parametrize("other_worker", [False, True])
def test_terminal_attempt_outcome_replays_or_conflicts(
    client,
    database,
    claim_worker,
    worker_factory,
    endpoint,
    field,
    status,
    same_payload,
    other_worker,
):
    worker, headers = claim_worker
    old_time = datetime(2020, 1, 1, tzinfo=UTC)
    stored = {"message": "original", "nested": [True, {"a": 1, "b": 2}]}
    result = stored if status == AttemptStatus.SUCCEEDED else None
    error = stored if status == AttemptStatus.FAILED else None
    payload = {
        field: {
            "nested": [True if same_payload else 1, {"b": 2, "a": 1.0}],
            "message": "original",
        }
    }
    with Session(database, expire_on_commit=False) as session:
        job_status = (
            JobStatus.FAILED
            if status == AttemptStatus.LOST
            else JobStatus(status.value)
        )
        job = Job(
            job_type="example",
            params={},
            status=job_status,
            user_id=worker.user_id,
            idempotency_key="terminal-outcome-test",
            request_fingerprint="unused",
            result=result,
            error=error,
            updated_at=old_time,
        )
        attempt = JobAttempt(
            job=job,
            worker_id=worker.id,
            attempt_number=1,
            params={},
            status=status,
            result=result,
            error=error,
            updated_at=old_time,
            lease_expires_at=old_time,
        )
        session.add(attempt)
        session.commit()
        job_id = job.id
        attempt_id = attempt.id

    if other_worker:
        _, headers = worker_factory()
    response = client.post(
        f"/workers/{attempt_id}/{endpoint}", headers=headers, json=payload
    )

    matches = same_payload and status.value == (
        "SUCCEEDED" if endpoint == "succeed" else "FAILED"
    )
    expected = 404 if other_worker else (200 if matches else 409)
    assert response.status_code == expected
    if expected == 200:
        assert response.json() == {"Status": "200 OK"}
    elif expected == 409:
        assert response.json() == {"detail": "Conflicting outcome report"}
    else:
        assert response.json() == {"detail": "Attempt not found"}
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.status == job_status
        assert job.result == result
        assert job.error == error
        assert job.updated_at == old_time
        attempt = session.get(JobAttempt, attempt_id)
        assert attempt.status == status
        assert attempt.result == result
        assert attempt.error == error
        assert attempt.updated_at == old_time
        assert attempt.lease_expires_at == old_time


@pytest.mark.parametrize(
    ("endpoint", "field"), [("succeed", "result"), ("fail", "error")]
)
@pytest.mark.parametrize(
    "target", ["missing", "other-worker", "no-key", "invalid-payload", "null-character"]
)
def test_outcome_rejection_preserves_running_attempt(
    client, database, claim_worker, worker_factory, endpoint, field, target
):
    worker, headers = claim_worker
    with Session(database) as session:
        job = Job(
            job_type="example",
            params={},
            user_id=worker.user_id,
            idempotency_key=uuid4().hex,
            request_fingerprint="test-fingerprint",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    claim = client.post("/workers/claim", headers=headers)
    assert claim.status_code == 200
    attempt_id = claim.json()["id"]
    target_id = attempt_id
    payload = {field: {"message": "outcome"}}
    expected = 404
    if target == "missing":
        target_id = 0
    elif target == "other-worker":
        _, headers = worker_factory()
    elif target == "no-key":
        headers = {}
        expected = 401
    elif target == "invalid-payload":
        payload = {field: []}
        expected = 422
    else:
        payload = {field: {"nested": ["\x00"]}}
        expected = 422

    response = client.post(
        f"/workers/{target_id}/{endpoint}", headers=headers, json=payload
    )
    assert response.status_code == expected
    if expected == 404:
        assert response.json() == {"detail": "Attempt not found"}
    with Session(database) as session:
        assert session.get(Job, job_id).status == JobStatus.RUNNING
        attempt = session.get(JobAttempt, attempt_id)
        assert attempt.status == AttemptStatus.RUNNING
        for record in (attempt, attempt.job):
            assert record.result is None
            assert record.error is None


@pytest.mark.parametrize("first_endpoint", ["succeed", "fail"])
@pytest.mark.parametrize("second_report", ["identical", "changed", "opposite"])
def test_concurrent_outcomes_serialize_and_preserve_first_report(
    client, database, claimed_attempt, first_endpoint, second_report
):
    from database import engine as api_engine
    from main import app

    claim, headers = claimed_attempt
    locked, release, waiting = Event(), Event(), Event()
    first_pid, waiting_pid = [], []
    first_snapshot = {}

    def hold_first_report(session, flush_context):
        if not locked.is_set() and any(
            isinstance(record, Job) and record.id == claim["job_id"]
            for record in session.dirty
        ):
            # Preserve the first report's timestamps too: the waiter must not rewrite them.
            for model in (JobAttempt, Job):
                first_snapshot[model] = (
                    session.execute(select(model.__table__)).mappings().one()
                )
            first_pid.append(
                session.connection().connection.driver_connection.info.backend_pid
            )
            locked.set()
            assert release.wait(timeout=20), "First report was never released"

    def observe_waiter(connection, cursor, statement, parameters, context, executemany):
        if (
            locked.is_set()
            and "FROM job_attempts" in statement
            and "FOR UPDATE" in statement
        ):
            waiting_pid.append(connection.connection.driver_connection.info.backend_pid)
            waiting.set()

    first_field = "result" if first_endpoint == "succeed" else "error"
    second_endpoint = (
        ("fail" if first_endpoint == "succeed" else "succeed")
        if second_report == "opposite"
        else first_endpoint
    )
    second_field = "result" if second_endpoint == "succeed" else "error"
    with TestClient(app) as other_client, ThreadPoolExecutor(max_workers=2) as executor:
        event.listen(Session, "after_flush", hold_first_report)
        event.listen(api_engine, "before_cursor_execute", observe_waiter)
        try:
            first_future = executor.submit(
                client.post,
                f"/workers/{claim['id']}/{first_endpoint}",
                headers=headers,
                json={first_field: {"value": 3}},
            )
            try:
                assert locked.wait(timeout=10), "First report never reached PostgreSQL"
                second_future = executor.submit(
                    other_client.post,
                    f"/workers/{claim['id']}/{second_endpoint}",
                    headers=headers,
                    json={
                        second_field: {"value": 4 if second_report == "changed" else 3}
                    },
                )
                assert waiting.wait(timeout=10), (
                    "Second report never attempted its lock"
                )
                with database.connect() as connection:
                    deadline = monotonic() + 10
                    while monotonic() < deadline:
                        if first_pid[0] in connection.scalar(
                            select(func.pg_blocking_pids(waiting_pid[0]))
                        ):
                            break
                    else:
                        pytest.fail("Second report did not wait for the attempt lock")
                assert not second_future.done()
            finally:
                release.set()
            first = first_future.result(timeout=10)
            second = second_future.result(timeout=10)
        finally:
            release.set()
            executor.shutdown(wait=True)
            event.remove(Session, "after_flush", hold_first_report)
            event.remove(api_engine, "before_cursor_execute", observe_waiter)

    assert first.status_code == 200
    assert second.status_code == (200 if second_report == "identical" else 409)
    if second_report != "identical":
        assert second.json() == {"detail": "Conflicting outcome report"}
    with Session(database) as session:
        for model in (JobAttempt, Job):
            stored = session.execute(select(model.__table__)).mappings().one()
            assert stored == first_snapshot[model]
            assert stored["status"].value == (
                "SUCCEEDED" if first_endpoint == "succeed" else "FAILED"
            )
            assert stored[first_field] == {"value": 3}
            assert stored["error" if first_field == "result" else "result"] is None


@pytest.mark.parametrize("endpoint", ["succeed", "fail"])
def test_outcome_database_failure_rolls_back_and_allows_retry(
    client, database, claimed_attempt, endpoint
):
    claim, headers = claimed_attempt
    with Session(database) as session:
        before = {
            model: session.execute(select(model.__table__)).mappings().one()
            for model in (JobAttempt, Job)
        }
    error = OperationalError(None, None, RuntimeError("Simulated database failure"))
    flushed = []

    def fail_after_flush(session, flush_context):
        if any(
            isinstance(record, Job) and record.id == claim["job_id"]
            for record in session.dirty
        ):
            flushed.append(True)
            raise error

    field = "result" if endpoint == "succeed" else "error"
    payload = {field: {"value": 3}}
    event.listen(Session, "after_flush", fail_after_flush)
    try:
        with pytest.raises(OperationalError) as raised:
            client.post(
                f"/workers/{claim['id']}/{endpoint}", headers=headers, json=payload
            )
        assert raised.value is error
    finally:
        event.remove(Session, "after_flush", fail_after_flush)
    assert flushed == [True]
    with Session(database) as session:
        for model in (JobAttempt, Job):
            assert (
                session.execute(select(model.__table__)).mappings().one()
                == before[model]
            )

    response = client.post(
        f"/workers/{claim['id']}/{endpoint}", headers=headers, json=payload
    )
    assert response.status_code == 200
    with Session(database) as session:
        attempt = session.get(JobAttempt, claim["id"])
        for record in (attempt, attempt.job):
            assert record.status.value == (
                "SUCCEEDED" if endpoint == "succeed" else "FAILED"
            )
            assert getattr(record, field) == payload[field]
            assert getattr(record, "error" if field == "result" else "result") is None
