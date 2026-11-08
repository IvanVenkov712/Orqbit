from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus, PermissionPolicy
from models.job_attempts import AttemptStatus, JobAttempt
from models.supported_types import SupportedJobType
from models.user import User
from models.worker import Worker


def test_create_and_read_job_preserves_json(client, database, user, user_headers):
    params = {
        "message": "Здравей",
        "options": {"enabled": True, "disabled": False},
        "values": [1, 2.5, None, {"nested": "value"}],
    }
    response = client.post(
        "/jobs/",
        headers=user_headers,
        json={"job_type": "example", "params": params, "permission_policy": "PRIVATE"},
    )

    assert response.status_code == 200
    created = response.json()
    assert isinstance(created["id"], int)
    assert created["job_type"] == "example"
    assert created["status"] == "PENDING"
    assert created["params"] == params
    assert created["result"] is None
    assert created["error"] is None
    assert created["user_id"] == user.id
    assert created["attempt_ids"] == []

    response = client.get(f"/jobs/{created['id']}", headers=user_headers)
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
        {"job_type": "", "params": {}},
        {"job_type": "   ", "params": {}},
        {"job_type": "x" * 101, "params": {}},
        {"job_type": "example", "params": {}, "permission_policy": "unknown"},
        {"job_type": "example", "params": {}, "permitted_user_ids": [0]},
        {"job_type": "example", "params": {}, "permitted_worker_ids": [-1]},
    ],
)
def test_invalid_submission_does_not_insert_job(
    client, database, user_headers, payload
):
    response = client.post(
        "/jobs/", headers=user_headers, json={"permission_policy": "PRIVATE", **payload}
    )

    assert response.status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_missing_job_returns_404(client, user_headers):
    response = client.get("/jobs/0", headers=user_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


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
                Job(job_type="unsupported", params={}, user_id=worker.user_id),
                Job(
                    job_type="example",
                    params={},
                    status=JobStatus.RUNNING,
                    user_id=worker.user_id,
                ),
                Job(job_type="example", params={}, user_id=worker.user_id),
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
        job = Job(job_type="example", params={}, user_id=worker.user_id)
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
        session.add(Job(job_type="example", params={}, user_id=worker.user_id))
        eligible = Job(job_type="updated", params={}, user_id=worker.user_id)
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


@pytest.mark.parametrize(
    ("endpoint", "field", "status"),
    [("succeed", "result", "SUCCEEDED"), ("fail", "error", "FAILED")],
)
def test_claim_and_report_outcome(
    client, database, user_headers, claim_worker, endpoint, field, status
):
    worker, headers = claim_worker
    response = client.post(
        "/jobs/",
        headers=user_headers,
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

    response = client.post("/workers/claim", headers=headers)
    assert response.status_code == 200
    attempt_id = response.json()["id"]
    assert response.json()["job_id"] == job_id
    assert response.json()["attempt_number"] == 1
    assert response.json()["params"] == {}
    assert response.json()["status"] == "RUNNING"
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.created_at == old_time
        assert job.updated_at > old_time
        assert job.updated_at.utcoffset() == timedelta(0)
        # Also independently verify the timestamp change on completion/failure.
        job.updated_at = old_time
        session.get(JobAttempt, attempt_id).updated_at = old_time
        session.commit()

    outcome = {"message": "Здравей", "values": [True, None, 3.5]}
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
        assert attempt.worker_id == worker.id
        assert attempt.status == AttemptStatus(status)
        assert getattr(attempt, field) == outcome
        assert getattr(attempt, other_field) is None
        assert attempt.updated_at > old_time


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [("succeed", {"result": {}}), ("fail", {"error": {"message": "failed"}})],
)
@pytest.mark.parametrize(
    "status", [AttemptStatus.SUCCEEDED, AttemptStatus.FAILED, AttemptStatus.LOST]
)
def test_non_running_attempt_rejects_outcome(
    client, database, claim_worker, endpoint, payload, status
):
    worker, headers = claim_worker
    old_time = datetime(2020, 1, 1, tzinfo=UTC)
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
            updated_at=old_time,
        )
        attempt = JobAttempt(
            job=job,
            worker_id=worker.id,
            attempt_number=1,
            params={},
            status=status,
            updated_at=old_time,
        )
        session.add(attempt)
        session.commit()
        job_id = job.id
        attempt_id = attempt.id

    response = client.post(
        f"/workers/{attempt_id}/{endpoint}", headers=headers, json=payload
    )

    assert response.status_code == 400
    detail = "Job not running" if endpoint == "succeed" else "Attempt not running"
    assert response.json() == {"detail": detail}
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert job.status == job_status
        assert job.result is None
        assert job.error is None
        assert job.updated_at == old_time
        attempt = session.get(JobAttempt, attempt_id)
        assert attempt.status == status
        assert attempt.result is None
        assert attempt.error is None
        assert attempt.updated_at == old_time


@pytest.mark.parametrize("path", ["/jobs/", "/jobs", "/jobs/0"])
def test_job_endpoints_require_user_token(client, path):
    response = client.post(path, json={}) if path == "/jobs/" else client.get(path)

    assert response.status_code == 401


def test_submission_requires_permission_policy(client, database, user_headers):
    response = client.post(
        "/jobs/", headers=user_headers, json={"job_type": "example", "params": {}}
    )

    assert response.status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize("field", ["permitted_user_ids", "permitted_worker_ids"])
def test_submission_rejects_nonexistent_permissions(
    client, database, user_headers, field
):
    response = client.post(
        "/jobs/",
        headers=user_headers,
        json={
            "job_type": "example",
            "params": {},
            "permission_policy": "ALL",
            field: [2147483647],
        },
    )

    assert response.status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


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


def test_list_jobs_filters_and_paginates(client, database, user, user_headers):
    with Session(database) as session:
        jobs = [
            Job(job_type="example", params={}, user_id=user.id),
            Job(job_type="other", params={}, user_id=user.id),
            Job(
                job_type="example", params={}, user_id=user.id, status=JobStatus.FAILED
            ),
            Job(job_type="example", params={}, user_id=user.id),
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
    ("endpoint", "field"), [("succeed", "result"), ("fail", "error")]
)
@pytest.mark.parametrize(
    "target", ["missing", "other-worker", "no-key", "invalid-payload"]
)
def test_outcome_rejection_preserves_running_attempt(
    client, database, claim_worker, worker_factory, endpoint, field, target
):
    worker, headers = claim_worker
    with Session(database) as session:
        job = Job(job_type="example", params={}, user_id=worker.user_id)
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
    else:
        payload = {field: []}
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
