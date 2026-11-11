"""Job submission, retrieval, and API input validation."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus


def test_create_and_read_job_preserves_json(client, database, user, user_headers):
    params = {
        "message": "Здравей",
        "options": {"enabled": True, "disabled": False},
        "values": [1, 2.5, None, {"nested": "value"}],
        "literal_escape": r"\u0000",
    }
    response = client.post(
        "/jobs/",
        headers={**user_headers, "Idempotency-Key": uuid4().hex},
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

    response = client.get(f"/jobs/{created['id']}/attempts", headers=user_headers)
    assert response.status_code == 200
    assert response.json() == []

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
        "/jobs/",
        headers={**user_headers, "Idempotency-Key": uuid4().hex},
        json={"permission_policy": "PRIVATE", **payload},
    )

    assert response.status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize("path", ["/jobs/0", "/jobs/0/attempts"])
def test_missing_job_returns_404(client, user_headers, path):
    response = client.get(path, headers=user_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


@pytest.mark.parametrize("path", ["/jobs/", "/jobs", "/jobs/0", "/jobs/0/attempts"])
def test_job_endpoints_require_user_token(client, path):
    response = client.post(path, json={}) if path == "/jobs/" else client.get(path)

    assert response.status_code == 401


def test_submission_requires_permission_policy(client, database, user_headers):
    response = client.post(
        "/jobs/",
        headers={**user_headers, "Idempotency-Key": uuid4().hex},
        json={"job_type": "example", "params": {}},
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
        headers={**user_headers, "Idempotency-Key": uuid4().hex},
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
