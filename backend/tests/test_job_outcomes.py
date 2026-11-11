"""Owned outcome reports, terminal replays, and rejected updates."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
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
