from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus


def test_create_and_read_job_preserves_json(client, database):
    params = {
        "message": "Здравей",
        "options": {"enabled": True, "disabled": False},
        "values": [1, 2.5, None, {"nested": "value"}],
    }
    response = client.post("/jobs/", json={"job_type": "example", "params": params})

    assert response.status_code == 200
    created = response.json()
    assert isinstance(created["id"], int)
    assert created["job_type"] == "example"
    assert created["status"] == "PENDING"
    assert created["params"] == params
    assert created["result"] is None
    assert created["error"] is None

    response = client.get(f"/jobs/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created

    # A separate connection confirms that the HTTP request committed the row.
    with Session(database) as session:
        job = session.get(Job, created["id"])
        assert job.params == params
        assert job.status == JobStatus.PENDING
        for timestamp in (job.created_at, job.updated_at):
            assert timestamp.utcoffset() == timedelta(0)
        assert job.updated_at >= job.created_at


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"job_type": "example"},
        {"params": {}},
        {"job_type": None, "params": {}},
        {"job_type": "example", "params": []},
        {"job_type": "example", "params": None},
    ],
)
def test_invalid_submission_does_not_insert_job(client, database, payload):
    response = client.post("/jobs/", json=payload)

    assert response.status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_missing_job_returns_404(client):
    response = client.get("/jobs/0")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_claim_selects_only_supported_pending_jobs(client, database):
    with Session(database) as session:
        session.add_all(
            [
                Job(job_type="unsupported", params={}),
                Job(job_type="example", params={}, status=JobStatus.RUNNING),
                Job(job_type="example", params={}),
            ]
        )
        session.commit()
        eligible_id = session.scalar(
            select(Job.id).where(
                Job.job_type == "example", Job.status == JobStatus.PENDING
            )
        )

    response = client.post("/workers/claim", json={"supported_types": ["example"]})

    assert response.status_code == 200
    assert response.json()["id"] == eligible_id
    assert response.json()["status"] == "RUNNING"
    with Session(database) as session:
        assert session.get(Job, eligible_id).status == JobStatus.RUNNING


def test_empty_queue_returns_404(client):
    response = client.post("/workers/claim", json={"supported_types": ["example"]})

    assert response.status_code == 404
    assert response.json() == {"detail": "No jobs were found"}


@pytest.mark.parametrize(
    ("endpoint", "field", "status"),
    [("succeed", "result", "SUCCEEDED"), ("fail", "error", "FAILED")],
)
def test_claim_and_report_outcome(client, database, endpoint, field, status):
    response = client.post("/jobs/", json={"job_type": "example", "params": {}})
    assert response.status_code == 200
    job_id = response.json()["id"]

    # A known earlier timestamp avoids sleeps and clock-resolution races.
    old_time = datetime(2020, 1, 1, tzinfo=UTC)
    with Session(database) as session:
        job = session.get(Job, job_id)
        job.created_at = old_time
        job.updated_at = old_time
        session.commit()

    response = client.post("/workers/claim", json={"supported_types": ["example"]})
    assert response.status_code == 200
    assert response.json()["id"] == job_id
    assert response.json()["status"] == "RUNNING"
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.created_at == old_time
        assert job.updated_at > old_time
        assert job.updated_at.utcoffset() == timedelta(0)
        # Also independently verify the timestamp change on completion/failure.
        job.updated_at = old_time
        session.commit()

    outcome = {"message": "Здравей", "values": [True, None, 3.5]}
    response = client.post(f"/workers/{job_id}/{endpoint}", json={field: outcome})
    assert response.status_code == 200

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()[field] == outcome
    other_field = "error" if field == "result" else "result"
    assert response.json()[other_field] is None
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.status == JobStatus(status)
        assert getattr(job, field) == outcome
        assert job.created_at == old_time
        assert job.updated_at > old_time
        assert job.updated_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [("succeed", {"result": {}}), ("fail", {"error": {"message": "failed"}})],
)
@pytest.mark.parametrize(
    "status", [JobStatus.PENDING, JobStatus.SUCCEEDED, JobStatus.FAILED]
)
def test_non_running_job_rejects_outcome(client, database, endpoint, payload, status):
    old_time = datetime(2020, 1, 1, tzinfo=UTC)
    with Session(database, expire_on_commit=False) as session:
        job = Job(job_type="example", params={}, status=status, updated_at=old_time)
        session.add(job)
        session.commit()
        job_id = job.id

    response = client.post(f"/workers/{job_id}/{endpoint}", json=payload)

    assert response.status_code == 400
    assert response.json() == {"detail": "Job not running"}
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.status == status
        assert job.result is None
        assert job.error is None
        assert job.updated_at == old_time
