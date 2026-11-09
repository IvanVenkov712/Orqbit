from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.job import Job, JobStatus, PermissionPolicy
from models.job_attempts import AttemptStatus, JobAttempt
from models.supported_types import SupportedJobType
from models.user import User
from models.worker import Worker


def test_submission_idempotency_persists_key_and_fingerprint(
    client, database, user, user_headers
):
    from dto.job import JobCreate
    from services.job import get_request_fingerprint

    payload = {"job_type": "example", "params": {}, "permission_policy": "PRIVATE"}
    key = "x" * 100
    response = client.post(
        "/jobs/", headers={**user_headers, "Idempotency-Key": key}, json=payload
    )

    assert response.status_code == 200
    with Session(database) as session:
        job = session.get(Job, response.json()["id"])
        assert job.idempotency_key == key
        assert job.request_fingerprint == get_request_fingerprint(JobCreate(**payload))
        assert job.user_id == user.id


@pytest.mark.parametrize("key", [None, "", "   ", "x" * 101])
def test_submission_idempotency_rejects_invalid_keys(
    client, database, user_headers, key
):
    response = client.post(
        "/jobs/",
        headers=user_headers
        if key is None
        else {**user_headers, "Idempotency-Key": key},
        json={"job_type": "example", "params": {}, "permission_policy": "PRIVATE"},
    )

    assert response.status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize("changed", [False, True])
def test_submission_idempotency_replays_or_conflicts(
    client, database, user_headers, changed
):
    payload = {"job_type": "example", "params": {}, "permission_policy": "PRIVATE"}
    headers = {**user_headers, "Idempotency-Key": "submission"}
    first = client.post("/jobs/", headers=headers, json=payload)
    assert first.status_code == 200
    with Session(database) as session:
        session.get(Job, first.json()["id"]).status = JobStatus.SUCCEEDED
        session.commit()

    if changed:
        payload["params"] = {"different": True}
    response = client.post("/jobs/", headers=headers, json=payload)

    assert response.status_code == (409 if changed else 200)
    if changed:
        assert response.json() == {"detail": "Conflicting create requests"}
    else:
        assert response.json()["id"] == first.json()["id"]
        assert response.json()["status"] == "SUCCEEDED"
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


@pytest.mark.parametrize("changed", [False, True])
def test_submission_idempotency_handles_concurrent_requests(
    client, database, user_headers, changed
):
    from main import app

    headers = {**user_headers, "Idempotency-Key": "concurrent-submission"}
    payload = {"job_type": "example", "params": {}, "permission_policy": "PRIVATE"}
    other_payload = {**payload, "params": {"different": True}} if changed else payload
    ready = Barrier(2)

    def wait_for_both_inserts(session, flush_context, instances):
        if any(
            isinstance(record, Job)
            and record.idempotency_key == headers["Idempotency-Key"]
            for record in session.new
        ):
            ready.wait(timeout=10)

    with TestClient(app) as other_client, ThreadPoolExecutor(max_workers=2) as executor:
        event.listen(Session, "before_flush", wait_for_both_inserts)
        try:
            first = executor.submit(
                client.post, "/jobs/", headers=headers, json=payload
            )
            second = executor.submit(
                other_client.post, "/jobs/", headers=headers, json=other_payload
            )
            responses = [first.result(timeout=20), second.result(timeout=20)]
        finally:
            executor.shutdown(wait=True)
            event.remove(Session, "before_flush", wait_for_both_inserts)

    assert sorted(response.status_code for response in responses) == (
        [200, 409] if changed else [200, 200]
    )
    if not changed:
        assert responses[0].json()["id"] == responses[1].json()["id"]
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_submission_idempotency_scopes_keys_to_creator(client, database, user_headers):
    from services.user_auth import create_access_token

    with Session(database) as session:
        other = User(
            username="another-creator",
            email="another-creator@example.com",
            full_name="Another creator",
            hashed_password="unused",
        )
        session.add(other)
        session.commit()
    payload = {"job_type": "example", "params": {}, "permission_policy": "PRIVATE"}
    first = client.post(
        "/jobs/", headers={**user_headers, "Idempotency-Key": "shared"}, json=payload
    )
    second = client.post(
        "/jobs/",
        headers={
            "Authorization": f"Bearer {create_access_token('another-creator')}",
            "Idempotency-Key": "shared",
        },
        json=payload,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.parametrize("error_type", [UniqueViolation, ForeignKeyViolation])
def test_submission_idempotency_preserves_unrelated_integrity_errors(
    client, database, user_headers, monkeypatch, error_type
):
    error = IntegrityError(None, None, error_type())

    def fail_commit(session):
        raise error

    monkeypatch.setattr(Session, "commit", fail_commit)

    with pytest.raises(IntegrityError) as raised:
        client.post(
            "/jobs/",
            headers={**user_headers, "Idempotency-Key": "submission"},
            json={"job_type": "example", "params": {}, "permission_policy": "PRIVATE"},
        )

    assert raised.value is error
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_submission_idempotency_normalizes_object_keys_and_permission_lists():
    from dto.job import JobCreate
    from services.job import get_request_fingerprint

    original = JobCreate(
        job_type="example",
        params={"b": {"y": 2, "x": 1}, "a": [1, 2]},
        permission_policy="PERMITTED_WORKERS_AND_USERS",
        permitted_user_ids=[7, 8, 7],
        permitted_worker_ids=[2, 1, 2],
    )
    reordered = original.model_copy(
        update={
            "params": {"a": [1, 2], "b": {"x": 1, "y": 2}},
            "permitted_user_ids": [8, 7],
            "permitted_worker_ids": [1, 2],
        }
    )
    assert get_request_fingerprint(original) == get_request_fingerprint(reordered)
    changed_array = reordered.model_copy(
        update={"params": {"a": [2, 1], "b": {"x": 1, "y": 2}}}
    )
    assert get_request_fingerprint(original) != get_request_fingerprint(changed_array)


def test_create_and_read_job_preserves_json(client, database, user, user_headers):
    params = {
        "message": "Здравей",
        "options": {"enabled": True, "disabled": False},
        "values": [1, 2.5, None, {"nested": "value"}],
        "literal_escape": r"\u0000",
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
        {"job_type": "example", "params": {"nested": ["\x00"]}},
        {"job_type": "example", "params": {"\x00": "value"}},
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
        assert attempt.worker_id == worker.id
        assert attempt.status == AttemptStatus(status)
        assert getattr(attempt, field) == outcome
        assert getattr(attempt, other_field) is None
        assert attempt.updated_at > old_time
        job_updated_at = job.updated_at
        attempt_updated_at = attempt.updated_at

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
@pytest.mark.parametrize("permission_id", [2147483647, 2**31, 2**63])
def test_submission_rejects_nonexistent_permissions(
    client, database, user_headers, field, permission_id
):
    response = client.post(
        "/jobs/",
        headers=user_headers,
        json={
            "job_type": "example",
            "params": {},
            "permission_policy": "ALL",
            field: [permission_id],
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
    "target", ["missing", "other-worker", "no-key", "invalid-payload", "null-character"]
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


@pytest.mark.parametrize("resource_id", [2**31, 2**63])
@pytest.mark.parametrize(
    "path",
    [
        "/jobs/{id}",
        "/jobs?owner_id={id}",
        "/workers/{id}",
        "/workers?owner_id={id}",
        "/workers/{id}/succeed",
        "/workers/{id}/fail",
    ],
)
def test_oversized_ids_return_422(
    client, user_headers, claim_worker, path, resource_id
):
    _, worker_headers = claim_worker
    path = path.format(id=resource_id)
    if path.endswith(("/succeed", "/fail")):
        field = "result" if path.endswith("/succeed") else "error"
        response = client.post(path, headers=worker_headers, json={field: {}})
    else:
        response = client.get(path, headers=user_headers)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Input contains a value PostgreSQL cannot store"
    }


def test_list_jobs_loads_attempts_in_one_query(
    client, database, user_headers, claim_worker
):
    from database import engine

    worker, _ = claim_worker
    with Session(database) as session:
        jobs = [
            Job(
                job_type="example",
                params={},
                user_id=worker.user_id,
                status=JobStatus.RUNNING,
                attempts=[JobAttempt(worker_id=worker.id, attempt_number=1, params={})],
            )
            for _ in range(3)
        ]
        session.add_all(jobs)
        session.commit()
        expected = {job.id: [attempt.id for attempt in job.attempts] for job in jobs}

    attempt_queries = []

    def count_attempt_queries(connection, cursor, statement, parameters, context, many):
        if "FROM job_attempts" in statement:
            attempt_queries.append(statement)

    event.listen(engine, "before_cursor_execute", count_attempt_queries)
    try:
        response = client.get("/jobs", headers=user_headers)
    finally:
        event.remove(engine, "before_cursor_execute", count_attempt_queries)

    assert response.status_code == 200
    assert {job["id"]: job["attempt_ids"] for job in response.json()} == expected
    assert len(attempt_queries) == 1


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
