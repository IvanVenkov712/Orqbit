"""Job lists and attempt history: ordering, pagination, and loading."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt


def test_job_attempt_history_orders_and_paginates(
    client, database, user_headers, claim_worker
):
    worker, _ = claim_worker
    with Session(database) as session:
        job = Job(
            job_type="example",
            params={},
            user_id=worker.user_id,
            status=JobStatus.FAILED,
            idempotency_key=uuid4().hex,
            request_fingerprint="test-fingerprint",
            # Insertion order deliberately differs from attempt-number order.
            attempts=[
                JobAttempt(
                    worker_id=worker.id,
                    attempt_number=number,
                    status=AttemptStatus.LOST,
                    params={},
                )
                for number in (2, 3, 1)
            ],
        )
        other_job = Job(
            job_type="other",
            params={},
            user_id=worker.user_id,
            idempotency_key=uuid4().hex,
            request_fingerprint="test-fingerprint",
            attempts=[JobAttempt(worker_id=worker.id, attempt_number=1, params={})],
        )
        session.add_all([job, other_job])
        session.commit()
        job_id = job.id

    response = client.get(f"/jobs/{job_id}/attempts", headers=user_headers)
    assert response.status_code == 200
    history = response.json()
    assert [attempt["attempt_number"] for attempt in history] == [3, 2, 1]
    assert all(attempt["job_id"] == job_id for attempt in history)
    assert all(attempt["status"] == "LOST" for attempt in history)

    response = client.get(
        f"/jobs/{job_id}/attempts",
        headers=user_headers,
        params={"limit": 1, "offset": 1},
    )
    assert response.status_code == 200
    assert response.json() == [history[1]]

    response = client.get(
        f"/jobs/{job_id}/attempts", headers=user_headers, params={"offset": 3}
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": "invalid"}]
)
def test_job_attempt_history_rejects_invalid_pagination(client, user_headers, params):
    response = client.get("/jobs/0/attempts", headers=user_headers, params=params)

    assert response.status_code == 422


def test_list_jobs_filters_and_paginates(client, database, user, user_headers):
    with Session(database) as session:
        jobs = [
            Job(
                job_type="example",
                params={},
                user_id=user.id,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
            ),
            Job(
                job_type="other",
                params={},
                user_id=user.id,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
            ),
            Job(
                job_type="example",
                params={},
                user_id=user.id,
                status=JobStatus.FAILED,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
            ),
            Job(
                job_type="example",
                params={},
                user_id=user.id,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
            ),
        ]
        session.add_all(jobs)
        session.commit()
        first_id, last_id = jobs[0].id, jobs[-1].id

    filters = {"owner_id": user.id, "job_type": "example", "status": "PENDING"}
    response = client.get("/jobs", headers=user_headers, params=filters)
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [last_id, first_id]
    response = client.get(
        "/jobs", headers=user_headers, params={**filters, "limit": 1, "offset": 1}
    )
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [first_id]


def test_list_jobs_orders_by_status_and_update_time_before_pagination(
    client, database, user, user_headers
):
    start = datetime(2026, 11, 10, tzinfo=UTC)
    with Session(database) as session:
        jobs = [
            Job(
                user_id=user.id,
                job_type="example",
                params={},
                status=status,
                created_at=start,
                updated_at=start + timedelta(hours=hours),
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
            )
            for status, hours in [
                (JobStatus.PENDING, 9),
                (JobStatus.FAILED, 10),
                (JobStatus.PENDING, 2),
                (JobStatus.RUNNING, 3),
                (JobStatus.SUCCEEDED, 6),
                (JobStatus.PENDING, 9),
            ]
        ]
        session.add_all(jobs)
        session.commit()
        ids = [job.id for job in jobs]

    params = {"owner_id": user.id, "sort": "status_updated"}
    expected = [ids[index] for index in (5, 0, 2, 3, 4, 1)]
    response = client.get("/jobs", headers=user_headers, params=params)
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == expected
    assert datetime.fromisoformat(response.json()[0]["created_at"]) == start
    assert datetime.fromisoformat(response.json()[0]["updated_at"]) == (
        start + timedelta(hours=9)
    )

    for offset in (0, 2, 4):
        response = client.get(
            "/jobs",
            headers=user_headers,
            params={**params, "limit": 2, "offset": offset},
        )
        assert response.status_code == 200
        assert [job["id"] for job in response.json()] == expected[offset : offset + 2]

    response = client.get(
        "/jobs", headers=user_headers, params={**params, "status": "PENDING"}
    )
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == expected[:3]

    # Existing API clients keep the default newest-ID-first ordering.
    response = client.get("/jobs", headers=user_headers)
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == ids[::-1]


def test_list_jobs_rejects_unknown_sort(client, user_headers):
    response = client.get("/jobs?sort=unknown", headers=user_headers)
    assert response.status_code == 422


@pytest.mark.parametrize("status", list(JobStatus))
def test_list_jobs_returns_summaries_without_loading_payloads_or_attempts(
    client, database, user_headers, claim_worker, status
):
    from database import engine

    worker, _ = claim_worker
    params = {"input": "x" * 1000}
    result = {"output": "y" * 1000} if status == JobStatus.SUCCEEDED else None
    error = {"message": "z" * 1000} if status == JobStatus.FAILED else None
    with Session(database) as session:
        jobs = [
            Job(
                job_type="example",
                params=params,
                user_id=worker.user_id,
                status=status,
                result=result,
                error=error,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
                attempts=[]
                if status == JobStatus.PENDING
                else [
                    JobAttempt(
                        worker_id=worker.id,
                        attempt_number=1,
                        params=params,
                        status=AttemptStatus(status.value),
                        result=result,
                        error=error,
                    )
                ],
            )
            for _ in range(3)
        ]
        session.add_all(jobs)
        session.commit()
        expected = {job.id: [attempt.id for attempt in job.attempts] for job in jobs}

    queries = []

    def record_queries(connection, cursor, statement, parameters, context, many):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", record_queries)
    try:
        response = client.get("/jobs", headers=user_headers)
    finally:
        event.remove(engine, "before_cursor_execute", record_queries)

    assert response.status_code == 200
    summaries = response.json()
    assert [job["id"] for job in summaries] == sorted(expected, reverse=True)
    for summary in summaries:
        assert set(summary) == {
            "id",
            "user_id",
            "job_type",
            "status",
            "created_at",
            "updated_at",
        }
        assert summary["user_id"] == worker.user_id
        assert summary["job_type"] == "example"
        assert summary["status"] == status.value
        for field in ("created_at", "updated_at"):
            assert datetime.fromisoformat(summary[field]).utcoffset() == timedelta(0)

    job_queries = [statement for statement in queries if "FROM jobs" in statement]
    assert len(job_queries) == 1
    selected_columns = job_queries[0].split("FROM jobs", 1)[0]
    for field in ("params", "result", "error"):
        assert f"jobs.{field}" not in selected_columns
    assert not any("FROM job_attempts" in statement for statement in queries)

    job_id = summaries[0]["id"]
    details = client.get(f"/jobs/{job_id}", headers=user_headers)
    assert details.status_code == 200
    assert details.json()["params"] == params
    assert details.json()["result"] == result
    assert details.json()["error"] == error
    assert details.json()["attempt_ids"] == expected[job_id]
