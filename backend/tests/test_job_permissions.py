"""Job permissions govern reads, lists, history, and claims."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus, PermissionPolicy
from models.job_attempts import JobAttempt
from models.user import User
from models.worker import Worker


@pytest.mark.parametrize(
    ("policy", "grant", "visible", "claimable"),
    [
        (PermissionPolicy.PRIVATE, None, False, False),
        (PermissionPolicy.ALL, None, True, True),
        (PermissionPolicy.PERMITTED_USERS, None, False, False),
        (PermissionPolicy.PERMITTED_USERS, "user", True, True),
        (PermissionPolicy.PERMITTED_WORKERS, None, False, False),
        (PermissionPolicy.PERMITTED_WORKERS, "worker", False, True),
        (PermissionPolicy.PERMITTED_WORKERS_AND_USERS, None, False, False),
        (PermissionPolicy.PERMITTED_WORKERS_AND_USERS, "user", True, True),
        (PermissionPolicy.PERMITTED_WORKERS_AND_USERS, "worker", False, True),
        # Grants only apply when the corresponding policy permits them.
        (PermissionPolicy.PRIVATE, "user", False, False),
        (PermissionPolicy.PERMITTED_USERS, "worker", False, False),
        (PermissionPolicy.PERMITTED_WORKERS, "user", False, False),
    ],
)
def test_job_permissions_control_reads_lists_and_claims(
    client,
    database,
    user,
    user_headers,
    claim_worker,
    policy,
    grant,
    visible,
    claimable,
):
    worker, headers = claim_worker
    with Session(database) as session:
        owner = User(
            username="other-owner",
            email="other@example.com",
            full_name="Other owner",
            hashed_password="unused",
        )
        job = Job(
            job_type="example",
            params={},
            user=owner,
            permission_policy=policy,
            idempotency_key=uuid4().hex,
            request_fingerprint="test-fingerprint",
            permitted_users=[session.get(User, user.id)] if grant == "user" else [],
            permitted_workers=[session.get(Worker, worker.id)]
            if grant == "worker"
            else [],
        )
        session.add(job)
        session.commit()
        job_id = job.id

    response = client.get(f"/jobs/{job_id}", headers=user_headers)
    assert response.status_code == (200 if visible else 404)
    response = client.get("/jobs", headers=user_headers)
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == ([job_id] if visible else [])

    response = client.post("/workers/claim", headers=headers)
    assert response.status_code == (200 if claimable else 404)
    with Session(database) as session:
        assert session.get(Job, job_id).status == (
            JobStatus.RUNNING if claimable else JobStatus.PENDING
        )
        attempts = session.scalars(select(JobAttempt)).all()
        assert len(attempts) == int(claimable)
        if claimable:
            assert response.json()["job_id"] == job_id
            assert attempts[0].worker_id == worker.id

    response = client.get(f"/jobs/{job_id}/attempts", headers=user_headers)
    assert response.status_code == (200 if visible else 404)
    if visible:
        assert [attempt["id"] for attempt in response.json()] == [
            attempt.id for attempt in attempts
        ]
    else:
        assert response.json() == {"detail": "Job not found"}
