"""Creator-scoped submission keys, replay, and concurrent requests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.user import User


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
