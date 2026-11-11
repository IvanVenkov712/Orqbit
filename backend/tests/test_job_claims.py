"""Claims use authenticated workers and their stored supported types."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import JobAttempt
from models.supported_types import SupportedJobType
from models.worker import Worker


@pytest.mark.parametrize(
    "body",
    [
        None,
        {"supported_types": ["unsupported"]},
        {"supported_types": []},
        {"supported_types": 123},
    ],
)
def test_claim_selects_only_supported_pending_jobs(
    client, database, claim_worker, body
):
    worker, headers = claim_worker
    with Session(database) as session:
        session.add(
            Worker(
                name="other-worker",
                user_id=worker.user_id,
                secret_api_key_hash="unused-other-worker-hash",
                supported_types=[SupportedJobType(type_name="unsupported")],
            )
        )
        session.add_all(
            [
                Job(
                    job_type="unsupported",
                    params={},
                    user_id=worker.user_id,
                    idempotency_key=uuid4().hex,
                    request_fingerprint="test-fingerprint",
                ),
                Job(
                    job_type="example",
                    params={},
                    status=JobStatus.RUNNING,
                    user_id=worker.user_id,
                    idempotency_key=uuid4().hex,
                    request_fingerprint="test-fingerprint",
                ),
                Job(
                    job_type="example",
                    params={},
                    user_id=worker.user_id,
                    idempotency_key=uuid4().hex,
                    request_fingerprint="test-fingerprint",
                ),
            ]
        )
        session.commit()
        eligible_id = session.scalar(
            select(Job.id).where(
                Job.job_type == "example", Job.status == JobStatus.PENDING
            )
        )

    response = client.post(
        "/workers/claim",
        headers=headers,
        **({"json": body} if body is not None else {}),
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == eligible_id
    assert response.json()["status"] == "RUNNING"
    with Session(database) as session:
        assert session.get(Job, eligible_id).status == JobStatus.RUNNING
        attempt = session.get(JobAttempt, response.json()["id"])
        assert attempt.job_id == eligible_id
        assert attempt.worker_id == worker.id
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 1


def test_empty_queue_returns_404(client, claim_worker):
    _, headers = claim_worker
    response = client.post("/workers/claim", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "No jobs were found"}


def test_claim_without_stored_types_cannot_use_request_body(
    client, database, claim_worker
):
    worker, headers = claim_worker
    with Session(database) as session:
        session.execute(
            delete(SupportedJobType).where(SupportedJobType.worker_id == worker.id)
        )
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

    response = client.post(
        "/workers/claim", headers=headers, json={"supported_types": ["example"]}
    )

    assert response.status_code == 404
    with Session(database) as session:
        assert session.get(Job, job_id).status == JobStatus.PENDING
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 0


def test_claim_uses_updated_stored_types(client, database, claim_worker):
    worker, headers = claim_worker
    with Session(database) as session:
        session.get(Worker, worker.id).supported_types = [
            SupportedJobType(type_name="updated")
        ]
        session.add(
            Job(
                job_type="example",
                params={},
                user_id=worker.user_id,
                idempotency_key=uuid4().hex,
                request_fingerprint="test-fingerprint",
            )
        )
        eligible = Job(
            job_type="updated",
            params={},
            user_id=worker.user_id,
            idempotency_key=uuid4().hex,
            request_fingerprint="test-fingerprint",
        )
        session.add(eligible)
        session.commit()
        eligible_id = eligible.id

    response = client.post("/workers/claim", headers=headers)

    assert response.status_code == 200
    assert response.json()["job_id"] == eligible_id
    assert response.json()["job_type"] == "updated"


def test_claim_requires_worker_api_key(client):
    response = client.post("/workers/claim")

    assert response.status_code == 401


def test_claim_openapi_has_no_request_body(client):
    operation = client.get("/openapi.json").json()["paths"]["/workers/claim"]["post"]

    assert "requestBody" not in operation


@pytest.mark.parametrize("inactive", [False, True])
def test_claim_rejects_invalid_or_inactive_worker(
    client, database, claim_worker, inactive
):
    worker, headers = claim_worker
    if inactive:
        with Session(database) as session:
            session.get(Worker, worker.id).active = False
            session.commit()
    else:
        headers = {"X-API-Key": "invalid-key"}

    assert client.post("/workers/claim", headers=headers).status_code == 401
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 0


@pytest.mark.parametrize(
    ("job_type", "expected_status"),
    [("", 422), ("   ", 422), ("x" * 101, 422), ("x" * 100, 200), ("example", 200)],
)
def test_worker_supported_types_use_job_type_rules(
    client, database, user_headers, job_type, expected_status
):
    response = client.post(
        "/workers",
        headers=user_headers,
        json={
            "name": "type-test",
            "permission_policy": "PRIVATE",
            "supported_types": [job_type],
        },
    )

    assert response.status_code == expected_status
    with Session(database) as session:
        workers = session.scalars(select(Worker)).all()
        assert len(workers) == int(expected_status == 200)
        if workers:
            assert [item.type_name for item in workers[0].supported_types] == [job_type]
