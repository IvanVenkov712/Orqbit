"""Bounded retries through PostgreSQL claims, recovery, and outcome reports."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt
from services import job_execution


@pytest.fixture
def scheduled_retry(client, database, claim_worker, job_factory):
    _, headers = claim_worker
    with Session(database) as session:
        session.add(job_factory(max_attempts=3, params={"input": [True, None, 3]}))
        session.commit()
    response = client.post("/workers/claim", headers=headers)
    assert response.status_code == 200
    claim = response.json()
    with Session(database) as session:
        now = session.scalar(select(func.clock_timestamp()))
        session.get(JobAttempt, claim["id"]).lease_expires_at = now - timedelta(days=1)
        session.commit()
        job_execution.recover_expired_attempts(session)
    return claim, headers


@pytest.mark.parametrize("max_attempts", [1, 3, 5])
def test_retries_preserve_history_until_budget_exhausted(
    client, database, user_headers, claim_worker, monkeypatch, max_attempts
):
    _, headers = claim_worker
    monkeypatch.setattr(job_execution.settings, "max_attempts", max_attempts)
    submission_headers = {**user_headers, "Idempotency-Key": uuid4().hex}
    payload = {
        "job_type": "example",
        "params": {"input": [True, None, 3]},
        "permission_policy": "PRIVATE",
    }
    response = client.post("/jobs/", headers=submission_headers, json=payload)
    assert response.status_code == 200
    created = response.json()
    job_id = created["id"]
    assert created["attempts_count"] == 0
    assert created["max_attempts"] == max_attempts

    # Configuration changes and submission replays must not reset this budget.
    monkeypatch.setattr(job_execution.settings, "max_attempts", 1)
    response = client.post("/jobs/", headers=submission_headers, json=payload)
    assert response.status_code == 200
    assert response.json() == created

    closed_attempts = []
    delays = [10, 20, 40, 60]
    for number in range(1, max_attempts + 1):
        response = client.post("/workers/claim", headers=headers)
        assert response.status_code == 200
        claim = response.json()
        assert claim["attempt_number"] == number
        assert claim["job_id"] == job_id
        assert claim["params"] == payload["params"]
        with Session(database) as session:
            job = session.get(Job, job_id)
            assert job.attempts_count == number
            assert job.max_attempts == max_attempts
            assert job.status == JobStatus.RUNNING
            now = session.scalar(select(func.clock_timestamp()))
            session.get(JobAttempt, claim["id"]).lease_expires_at = now - timedelta(
                days=1
            )
            session.commit()

        # Keep the retry in the future regardless of how long the test takes.
        recovery_now = now + timedelta(days=1)
        with monkeypatch.context() as clock:
            clock.setattr(job_execution, "get_db_now", lambda session: recovery_now)
            with Session(database) as session:
                job_execution.recover_expired_attempts(session)

        job_response = client.get(f"/jobs/{job_id}", headers=user_headers)
        assert job_response.status_code == 200
        recovered = job_response.json()
        assert recovered["attempts_count"] == number
        assert recovered["max_attempts"] == max_attempts
        assert recovered["result"] is None
        if number < max_attempts:
            assert recovered["status"] == "PENDING"
            assert recovered["error"] is None
            assert datetime.fromisoformat(recovered["available_at"]) == (
                recovery_now + timedelta(seconds=delays[number - 1])
            )
        else:
            assert recovered["status"] == "FAILED"
            assert recovered["error"] == {
                "code": "attempts_exhausted",
                "message": "Maximum attempts reached after lease expiry",
            }

        history_response = client.get(f"/jobs/{job_id}/attempts", headers=user_headers)
        assert history_response.status_code == 200
        history = history_response.json()
        closed_attempts.append(history[0])
        assert history == list(reversed(closed_attempts))
        assert [attempt["attempt_number"] for attempt in history] == list(
            range(number, 0, -1)
        )
        assert all(attempt["status"] == "LOST" for attempt in history)
        assert all(attempt["params"] == payload["params"] for attempt in history)
        assert all(
            attempt["result"] is None and attempt["error"] is None
            for attempt in history
        )

        # Fresh sessions model a later recovery scan and API request after restart.
        with Session(database) as session:
            job_execution.recover_expired_attempts(session)
        assert client.get(f"/jobs/{job_id}", headers=user_headers).json() == recovered
        assert client.post("/workers/claim", headers=headers).status_code == 404
        assert (
            client.get(f"/jobs/{job_id}/attempts", headers=user_headers).json()
            == history
        )

        if number < max_attempts:
            # Make the persisted schedule due without sleeping or changing clocks.
            with Session(database) as session:
                session.get(Job, job_id).available_at = session.scalar(
                    select(func.clock_timestamp())
                ) - timedelta(days=1)
                session.commit()


@pytest.mark.parametrize("blocked_by", ["future", "budget"])
def test_claim_skips_retries_that_are_not_due_or_have_no_budget(
    client, database, scheduled_retry, job_factory, blocked_by
):
    claim, headers = scheduled_retry
    with Session(database) as session:
        job = session.get(Job, claim["job_id"])
        now = session.scalar(select(func.clock_timestamp()))
        job.available_at = now + timedelta(days=1)
        if blocked_by == "budget":
            job.max_attempts = job.attempts_count
            job.available_at = now - timedelta(days=1)
        session.commit()
        before = session.execute(select(Job.__table__)).mappings().one()

    assert client.post("/workers/claim", headers=headers).status_code == 404
    with Session(database) as session:
        assert session.execute(select(Job.__table__)).mappings().one() == before
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 1
        eligible = job_factory()
        session.add(eligible)
        session.commit()
        eligible_id = eligible.id

    response = client.post("/workers/claim", headers=headers)
    assert response.status_code == 200
    assert response.json()["job_id"] == eligible_id


@pytest.mark.parametrize("same_worker", [True, False])
@pytest.mark.parametrize("outcome", ["succeed", "fail"])
def test_retry_rejects_stale_reports_and_accepts_current_outcome_replays(
    client,
    database,
    user_headers,
    scheduled_retry,
    worker_factory,
    same_worker,
    outcome,
):
    old_claim, old_headers = scheduled_retry
    headers = old_headers if same_worker else worker_factory()[1]
    with Session(database) as session:
        session.get(Job, old_claim["job_id"]).available_at = session.scalar(
            select(func.clock_timestamp())
        ) - timedelta(days=1)
        session.commit()
    response = client.post("/workers/claim", headers=headers)
    assert response.status_code == 200
    claim = response.json()
    assert claim["id"] != old_claim["id"]
    assert claim["attempt_number"] == 2

    field = "result" if outcome == "succeed" else "error"
    payload = {field: {"current": True}}
    for phase in ("running", "terminal"):
        with Session(database) as session:
            before = {
                model: session.execute(select(model.__table__).order_by(model.id))
                .mappings()
                .all()
                for model in (Job, JobAttempt)
            }
        for endpoint, body, status in (
            ("heartbeat", {}, 400),
            ("succeed", {"result": {"stale": True}}, 409),
            ("fail", {"error": {"stale": True}}, 409),
        ):
            response = client.post(
                f"/workers/{old_claim['id']}/{endpoint}", headers=old_headers, json=body
            )
            assert response.status_code == status
        with Session(database) as session:
            for model in (Job, JobAttempt):
                assert (
                    session.execute(select(model.__table__).order_by(model.id))
                    .mappings()
                    .all()
                    == before[model]
                )
        response = client.post(
            f"/workers/{claim['id']}/{outcome}", headers=headers, json=payload
        )
        assert response.status_code == 200
        if phase == "terminal":
            with Session(database) as session:
                job_execution.recover_expired_attempts(session)
                for model in (Job, JobAttempt):
                    assert (
                        session.execute(select(model.__table__).order_by(model.id))
                        .mappings()
                        .all()
                        == before[model]
                    )

    response = client.get(f"/jobs/{claim['job_id']}", headers=user_headers)
    assert response.status_code == 200
    job = response.json()
    assert job["status"] == ("SUCCEEDED" if outcome == "succeed" else "FAILED")
    assert job[field] == payload[field]
    assert job["attempts_count"] == 2
    assert job["max_attempts"] == 3
    assert client.post("/workers/claim", headers=headers).status_code == 404


def test_retry_claim_failure_rolls_back_counter_and_attempt(
    client, database, scheduled_retry
):
    claim, headers = scheduled_retry
    with Session(database) as session:
        session.get(Job, claim["job_id"]).available_at = session.scalar(
            select(func.clock_timestamp())
        ) - timedelta(days=1)
        session.commit()
        before = {
            model: session.execute(select(model.__table__)).mappings().one()
            for model in (Job, JobAttempt)
        }

    def fail_after_flush(session, flush_context):
        if any(isinstance(record, JobAttempt) for record in session.new):
            raise RuntimeError("Simulated retry claim failure")

    event.listen(Session, "after_flush", fail_after_flush)
    try:
        with pytest.raises(RuntimeError, match="Simulated retry claim failure"):
            client.post("/workers/claim", headers=headers)
    finally:
        event.remove(Session, "after_flush", fail_after_flush)

    with Session(database) as session:
        for model in (Job, JobAttempt):
            assert (
                session.execute(select(model.__table__)).mappings().one()
                == before[model]
            )
    response = client.post("/workers/claim", headers=headers)
    assert response.status_code == 200
    assert response.json()["attempt_number"] == 2
    with Session(database) as session:
        assert session.get(Job, claim["job_id"]).attempts_count == 2
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 2


def test_overlapping_retry_claims_create_only_one_new_attempt(
    client, database, scheduled_retry, claim_worker, worker_factory
):
    claim, first_headers = scheduled_retry
    first_worker, _ = claim_worker
    _, second_headers = worker_factory()
    with Session(database) as session:
        session.get(Job, claim["job_id"]).available_at = session.scalar(
            select(func.clock_timestamp())
        ) - timedelta(days=1)
        session.commit()
    locked, release = Event(), Event()

    def hold_first_claim(session, flush_context):
        if any(
            isinstance(record, JobAttempt) and record.worker_id == first_worker.id
            for record in session.new
        ):
            locked.set()
            assert release.wait(timeout=20), "Retry claim was never released"

    from main import app

    with TestClient(app) as other_client, ThreadPoolExecutor(max_workers=2) as executor:
        event.listen(Session, "after_flush", hold_first_claim)
        try:
            first_future = executor.submit(
                client.post, "/workers/claim", headers=first_headers
            )
            try:
                assert locked.wait(timeout=10), "Retry claim never reached its flush"
                second = executor.submit(
                    other_client.post, "/workers/claim", headers=second_headers
                ).result(timeout=10)
                assert second.status_code == 404
            finally:
                release.set()
            first = first_future.result(timeout=10)
        finally:
            release.set()
            executor.shutdown(wait=True)
            event.remove(Session, "after_flush", hold_first_claim)

    assert first.status_code == 200
    assert first.json()["attempt_number"] == 2
    with Session(database) as session:
        job = session.get(Job, claim["job_id"])
        assert job.attempts_count == 2
        attempts = session.scalars(
            select(JobAttempt).order_by(JobAttempt.attempt_number)
        ).all()
        assert [attempt.status for attempt in attempts] == [
            AttemptStatus.LOST,
            AttemptStatus.RUNNING,
        ]
        assert [attempt.attempt_number for attempt in attempts] == [1, 2]
        assert attempts[1].worker_id == first_worker.id
