"""Claims overlap in real PostgreSQL transactions, synchronized without sleeps."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt


@pytest.mark.parametrize("job_count", [1, 2], ids=["one-job", "two-jobs"])
def test_overlapping_claims_skip_locked_jobs(
    client, database, user, worker_factory, job_count
):
    first_worker, first_headers = worker_factory()
    second_worker, second_headers = worker_factory()
    with Session(database) as session:
        jobs = [
            Job(
                job_type="example",
                params={"index": index},
                user_id=user.id,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
            )
            for index in range(job_count)
        ]
        session.add_all(jobs)
        session.commit()
        job_ids = [job.id for job in jobs]

    locked = Event()
    release = Event()

    def hold_first_claim(session, flush_context):
        if any(
            isinstance(record, JobAttempt) and record.worker_id == first_worker.id
            for record in session.new
        ):
            # Both the job update and attempt insert have reached PostgreSQL,
            # but the request has not committed its transaction yet.
            locked.set()
            assert release.wait(timeout=20), "First claim was never released"

    from main import app

    with TestClient(app) as other_client, ThreadPoolExecutor(max_workers=2) as executor:
        event.listen(Session, "after_flush", hold_first_claim)
        try:
            first_future = executor.submit(
                client.post, "/workers/claim", headers=first_headers
            )
            try:
                assert locked.wait(timeout=10), "First claim never reached its flush"
                second_future = executor.submit(
                    other_client.post, "/workers/claim", headers=second_headers
                )
                # The second request must finish while the first remains locked.
                second = second_future.result(timeout=10)
            finally:
                release.set()
            first = first_future.result(timeout=10)
        finally:
            release.set()
            # Drain requests before removing the listener or cleaning up data.
            executor.shutdown(wait=True)
            event.remove(Session, "after_flush", hold_first_claim)

    assert first.status_code == 200
    assert first.json()["job_id"] == job_ids[0]
    if job_count == 1:
        assert second.status_code == 404
        assert second.json() == {"detail": "No jobs were found"}
    else:
        assert second.status_code == 200
        assert second.json()["job_id"] == job_ids[1]
        assert second.json()["id"] != first.json()["id"]

    with Session(database) as session:
        attempts = session.scalars(select(JobAttempt).order_by(JobAttempt.job_id)).all()
        assert [attempt.job_id for attempt in attempts] == job_ids
        assert [attempt.worker_id for attempt in attempts] == (
            [first_worker.id] if job_count == 1 else [first_worker.id, second_worker.id]
        )
        for index, attempt in enumerate(attempts):
            assert attempt.status == AttemptStatus.RUNNING
            assert attempt.attempt_number == 1
            assert attempt.params == {"index": index}
            assert attempt.job.status == JobStatus.RUNNING


def test_failed_claim_rolls_back_and_releases_job(
    client, database, user, worker_factory
):
    _, first_headers = worker_factory()
    second_worker, second_headers = worker_factory()
    with Session(database) as session:
        job = Job(
            job_type="example",
            params={"preserved": True},
            user_id=user.id,
            idempotency_key=uuid4().hex,
            request_fingerprint="test-fingerprint",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    def fail_after_flush(session, flush_context):
        if any(isinstance(record, JobAttempt) for record in session.new):
            raise RuntimeError("Simulated claim failure after flush")

    event.listen(Session, "after_flush", fail_after_flush)
    try:
        with pytest.raises(RuntimeError, match="Simulated claim failure after flush"):
            client.post("/workers/claim", headers=first_headers)
    finally:
        event.remove(Session, "after_flush", fail_after_flush)

    with Session(database) as session:
        assert session.get(Job, job_id).status == JobStatus.PENDING
        assert session.scalars(select(JobAttempt)).all() == []

    response = client.post("/workers/claim", headers=second_headers)
    assert response.status_code == 200
    assert response.json()["job_id"] == job_id
    assert response.json()["params"] == {"preserved": True}
    with Session(database) as session:
        attempt = session.scalars(select(JobAttempt)).one()
        assert attempt.worker_id == second_worker.id
        assert attempt.attempt_number == 1
        assert attempt.job.status == JobStatus.RUNNING
