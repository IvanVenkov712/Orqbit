"""Worker registration, credential secrecy, and permission-aware discovery."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt
from models.job_permitted_workers import PermittedWorker
from models.supported_types import SupportedJobType
from models.user import User
from models.worker import PermissionPolicy, Worker
from models.worker_permitted_users import WorkerPermittedUser
from services.worker_auth import hash_api_key


@pytest.mark.parametrize("owner_filter", ["owner_id", "owner_username"])
def test_worker_creation_and_active_filters_preserve_access_and_pagination(
    client, database, user, user_headers, owner_filter
):
    start = datetime(2026, 11, 10, tzinfo=UTC)
    with Session(database) as session:
        owner = User(
            username="other-owner", email="other@example.com",
            full_name="Other", hashed_password="unused",
        )
        session.add(owner)
        session.flush()
        workers = []
        for index, (policy, hours, job_type, active) in enumerate([
            (PermissionPolicy.ALL, -1, "example", False),
            (PermissionPolicy.ALL, 0, "example", False),
            (PermissionPolicy.PERMITTED_USERS, 1, "example", False),
            (PermissionPolicy.PRIVATE, 2, "example", False),
            (PermissionPolicy.ALL, 3, "other", False),
            (PermissionPolicy.ALL, 4, "example", True),
            (PermissionPolicy.ALL, 5, "example", False),
        ]):
            worker = Worker(
                name=f"filtered-{index}", user_id=owner.id, active=active,
                permission_policy=policy, secret_api_key_hash=f"unused-{index}",
                created_at=start + timedelta(hours=hours),
                supported_types=[SupportedJobType(type_name=job_type)],
                permitted_users=[session.get(User, user.id)]
                if policy == PermissionPolicy.PERMITTED_USERS else [],
            )
            session.add(worker)
            workers.append(worker)
        session.commit()
        owner_id = owner.id
        expected = [workers[2].id, workers[1].id]
        active_id = workers[5].id

    filters = {
        owner_filter: owner_id if owner_filter == "owner_id" else "other-owner",
        "job_type": "example", "active": "false",
        "created_from": "2026-11-10T02:00:00+02:00",
        "created_before": (start + timedelta(hours=5)).isoformat(),
    }
    response = client.get("/workers", headers=user_headers, params=filters)
    assert response.status_code == 200
    assert [worker["id"] for worker in response.json()] == expected
    assert all(worker["owner_username"] == "other-owner" for worker in response.json())
    response = client.get(
        "/workers", headers=user_headers, params={**filters, "limit": 1, "offset": 1}
    )
    assert [worker["id"] for worker in response.json()] == expected[1:]
    response = client.get(
        "/workers", headers=user_headers, params={**filters, "active": "true"}
    )
    assert [worker["id"] for worker in response.json()] == [active_id]
    del filters["active"]
    response = client.get("/workers", headers=user_headers, params=filters)
    assert [worker["id"] for worker in response.json()] == [active_id, *expected]
    for username in ("missing-owner", "other", "other%", "OTHER-OWNER"):
        response = client.get(
            "/workers", headers=user_headers,
            params={**filters, "owner_username": username},
        )
        assert response.status_code == 200
        assert response.json() == []
    details = client.get(f"/workers/{expected[0]}", headers=user_headers)
    assert details.json()["owner_username"] == "other-owner"


def test_list_workers_rejects_invalid_active_filter(client, user_headers):
    response = client.get("/workers", headers=user_headers, params={"active": "LOST"})
    assert response.status_code == 422


@pytest.mark.parametrize("sort, order", [
    ("created_asc", [0, 2, 1, 3]), ("created_desc", [3, 2, 1, 0]),
    ("name_asc", [2, 1, 3, 0]), ("name_desc", [0, 3, 1, 2]),
    ("owner_asc", [3, 1, 2, 0]), ("owner_desc", [2, 0, 3, 1]),
    ("active_asc", [3, 1, 2, 0]), ("active_desc", [2, 0, 3, 1]),
])
def test_worker_column_sorts_preserve_visibility_and_order_before_paging(
    client, database, user, user_headers, sort, order
):
    start = datetime(2026, 11, 10, tzinfo=UTC)
    with Session(database) as session:
        other = User(
            username="alpha", email="alpha@example.com",
            full_name="Alpha", hashed_password="unused",
        )
        session.add(other)
        session.flush()
        workers = [
            Worker(
                name=name, user_id=owner_id, active=active,
                permission_policy=PermissionPolicy.ALL, secret_api_key_hash=name,
                created_at=start + timedelta(hours=hours),
                supported_types=[SupportedJobType(type_name="example")],
            )
            for name, owner_id, active, hours in [
                ("zeta", user.id, True, 1), ("beta", other.id, False, 2),
                ("alpha", user.id, True, 2), ("gamma", other.id, False, 3),
            ]
        ]
        session.add_all(workers)
        session.add(Worker(
            name="hidden", user_id=other.id, permission_policy=PermissionPolicy.PRIVATE,
            secret_api_key_hash="hidden", supported_types=[SupportedJobType(type_name="example")],
        ))
        session.commit()
        expected = [workers[index].id for index in order]

    for offset, limit in [(0, 50), (0, 2), (2, 2)]:
        response = client.get("/workers", headers=user_headers, params={
            "sort": sort, "offset": offset, "limit": limit,
        })
        assert response.status_code == 200
        assert [worker["id"] for worker in response.json()] == expected[offset:offset + limit]


def test_list_workers_rejects_unknown_sort(client, user_headers):
    response = client.get("/workers?sort=unknown", headers=user_headers)
    assert response.status_code == 422


def test_registered_worker_key_claims_and_is_not_exposed_by_reads(
    client, database, user, user_headers
):
    response = client.post(
        "/workers",
        headers=user_headers,
        json={
            "name": "registered",
            "supported_types": ["example", "example"],
            "permission_policy": "PRIVATE",
        },
    )
    assert response.status_code == 200
    created = response.json()
    key = created.pop("secret_api_key")
    assert key.startswith("oqb_")
    assert created["user_id"] == user.id
    assert created["owner_username"] == user.username
    assert created["supported_types"] == ["example"]
    with Session(database) as session:
        stored = session.get(Worker, created["id"])
        assert stored.secret_api_key_hash == hash_api_key(key)
        assert stored.secret_api_key_hash != key
        session.add(
            Job(
                user_id=user.id,
                job_type="example",
                params={"input": True},
                idempotency_key="registered-worker",
                request_fingerprint="test",
            )
        )
        session.commit()
    claim = client.post("/workers/claim", headers={"X-API-Key": key})
    assert claim.status_code == 200
    with Session(database) as session:
        assert session.get(JobAttempt, claim.json()["id"]).worker_id == created["id"]
    for path, expected in [
        (f"/workers/{created['id']}", created),
        ("/workers", [created]),
    ]:
        response = client.get(path, headers=user_headers)
        assert response.status_code == 200
        assert response.json() == expected
        assert key not in response.text
        assert hash_api_key(key) not in response.text


@pytest.mark.parametrize("case", ["duplicate-name", "missing-user"])
def test_rejected_worker_registration_leaves_no_partial_records(
    client, database, user, user_headers, case
):
    payload = {
        "name": "registered",
        "supported_types": ["example"],
        "permission_policy": "PERMITTED_USERS",
        "permitted_user_ids": [user.id],
    }
    if case == "duplicate-name":
        assert (
            client.post("/workers", headers=user_headers, json=payload).status_code
            == 200
        )
    else:
        payload["permitted_user_ids"] = [user.id, user.id + 10000]
    with Session(database) as session:
        before = {
            table.name: session.execute(select(table)).mappings().all()
            for table in (
                Worker.__table__,
                SupportedJobType.__table__,
                WorkerPermittedUser.__table__,
            )
        }
    response = client.post("/workers", headers=user_headers, json=payload)
    assert response.status_code == (409 if case == "duplicate-name" else 422)
    assert response.json() == {
        "detail": (
            "Worker name already exists"
            if case == "duplicate-name"
            else "Some permitted users do not exist"
        )
    }
    with Session(database) as session:
        for table in (
            Worker.__table__,
            SupportedJobType.__table__,
            WorkerPermittedUser.__table__,
        ):
            assert session.execute(select(table)).mappings().all() == before[table.name]


@pytest.mark.parametrize(
    ("policy", "owned", "granted", "visible"),
    [
        ("PRIVATE", True, False, True),
        ("PERMITTED_USERS", True, False, True),
        ("ALL", True, False, True),
        ("PRIVATE", False, False, False),
        ("PRIVATE", False, True, False),
        ("PERMITTED_USERS", False, False, False),
        ("PERMITTED_USERS", False, True, True),
        ("ALL", False, False, True),
    ],
)
def test_worker_visibility_applies_to_details_and_lists(
    client, database, user, user_headers, policy, owned, granted, visible
):
    with Session(database) as session:
        owner = (
            session.get(User, user.id)
            if owned
            else User(
                username="other-owner",
                email="other@example.com",
                full_name="Other",
                hashed_password="unused",
            )
        )
        worker = Worker(
            name="visible-worker",
            user=owner,
            secret_api_key_hash="unused",
            permission_policy=PermissionPolicy(policy),
            supported_types=[SupportedJobType(type_name="example")],
            permitted_users=[session.get(User, user.id)] if granted else [],
        )
        session.add(worker)
        session.commit()
        worker_id = worker.id
    response = client.get(f"/workers/{worker_id}", headers=user_headers)
    assert response.status_code == (200 if visible else 404)
    if not visible:
        assert response.json() == {"detail": "Worker not found"}
    response = client.get("/workers", headers=user_headers)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ([worker_id] if visible else [])


def test_worker_filters_apply_before_ordering_and_pagination(
    client, database, user, user_headers
):
    with Session(database) as session:
        other = User(
            username="other-owner",
            email="other@example.com",
            full_name="Other",
            hashed_password="unused",
        )
        session.add(other)
        session.flush()
        records = []
        for index, (owner_id, types, policy) in enumerate(
            [
                (user.id, ["example", "extra"], PermissionPolicy.PRIVATE),
                (user.id, ["example"], PermissionPolicy.ALL),
                (user.id, ["different"], PermissionPolicy.PRIVATE),
                (other.id, ["example"], PermissionPolicy.ALL),
                (other.id, ["example"], PermissionPolicy.PRIVATE),
            ]
        ):
            worker = Worker(
                name=f"worker-{index}",
                user_id=owner_id,
                secret_api_key_hash=f"hash-{index}",
                permission_policy=policy,
                supported_types=[SupportedJobType(type_name=value) for value in types],
            )
            session.add(worker)
            session.flush()
            records.append(worker.id)
        session.commit()
    for params, expected in [
        ({}, records[3::-1]),
        ({"owner_id": user.id}, records[2::-1]),
        ({"job_type": "example"}, [records[3], records[1], records[0]]),
        ({"owner_id": user.id, "job_type": "example", "limit": 1}, [records[1]]),
        (
            {"owner_id": user.id, "job_type": "example", "limit": 1, "offset": 1},
            [records[0]],
        ),
        ({"owner_id": user.id, "job_type": "example", "offset": 2}, []),
    ]:
        response = client.get("/workers", headers=user_headers, params=params)
        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == expected


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_worker_list_rejects_invalid_pagination(client, user_headers, params):
    assert (
        client.get("/workers", headers=user_headers, params=params).status_code == 422
    )


@pytest.mark.parametrize("path", ["/workers", "/workers/1"])
def test_worker_reads_require_user_authentication(client, path):
    assert client.get(path).status_code == 401


def test_worker_registration_requires_user_authentication(client, database):
    response = client.post(
        "/workers",
        json={
            "name": "registered",
            "supported_types": ["example"],
            "permission_policy": "PRIVATE",
        },
    )
    assert response.status_code == 401
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Worker)) == 0


def test_update_worker_types_replaces_capabilities_and_changes_claim_eligibility(
    client, database, user_headers, job_factory
):
    created = client.post("/workers", headers=user_headers, json={
        "name": "managed-worker",
        "supported_types": ["example", "retained"],
        "permission_policy": "PRIVATE",
    }).json()
    key = created.pop("secret_api_key")
    with Session(database) as session:
        removed_job = job_factory(job_type="example")
        added_job = job_factory(job_type="new")
        session.add_all([removed_job, added_job])
        session.commit()
        removed_id, added_id = removed_job.id, added_job.id

    path = f"/workers/{created['id']}/supported-types"
    for _ in range(2):
        response = client.put(path, headers=user_headers, json={
            "supported_types": ["retained", "new", "new"],
        })
        assert response.status_code == 200
        updated = response.json()
        assert set(updated.pop("supported_types")) == {"retained", "new"}
        assert updated == {k: v for k, v in created.items() if k != "supported_types"}
        assert key not in response.text
        assert hash_api_key(key) not in response.text

    with Session(database) as session:
        worker = session.get(Worker, created["id"])
        assert {t.type_name for t in worker.supported_types} == {"retained", "new"}
        assert worker.secret_api_key_hash == hash_api_key(key)
    claim = client.post("/workers/claim", headers={"X-API-Key": key})
    assert claim.status_code == 200
    assert claim.json()["job_id"] == added_id
    with Session(database) as session:
        assert session.get(Job, removed_id).status == JobStatus.PENDING


@pytest.mark.parametrize("payload", [
    {}, {"supported_types": []}, {"supported_types": [""]},
    {"supported_types": [" \t"]}, {"supported_types": ["a" * 101]},
    {"supported_types": [None]}, {"supported_types": [123]},
])
def test_update_worker_types_rejects_invalid_payload_without_changes(
    client, database, claim_worker, user_headers, payload
):
    worker, _ = claim_worker
    response = client.put(
        f"/workers/{worker.id}/supported-types", headers=user_headers, json=payload,
    )
    assert response.status_code == 422
    with Session(database) as session:
        assert {t.type_name for t in session.get(Worker, worker.id).supported_types} == {
            "example"
        }


def test_reissued_worker_key_replaces_old_key_and_is_not_exposed_by_reads(
    client, database, user_headers, job_factory
):
    created = client.post("/workers", headers=user_headers, json={
        "name": "managed-worker",
        "supported_types": ["example"],
        "permission_policy": "PRIVATE",
    }).json()
    worker_id = created["id"]
    old_headers = {"X-API-Key": created.pop("secret_api_key")}
    with Session(database) as session:
        session.add(job_factory())
        session.commit()
    claim = client.post("/workers/claim", headers=old_headers)
    assert claim.status_code == 200
    attempt_id = claim.json()["id"]
    response = client.post(f"/workers/{worker_id}/api-key", headers=user_headers)
    assert response.status_code == 200
    assert set(response.json()) == {"secret_api_key"}
    key = response.json()["secret_api_key"]
    assert key.startswith("oqb_")
    assert key != old_headers["X-API-Key"]
    with Session(database) as session:
        stored = session.get(Worker, worker_id)
        assert stored.secret_api_key_hash == hash_api_key(key)
        session.add(job_factory())
        session.commit()
    assert client.post("/workers/claim", headers=old_headers).status_code == 401
    new_headers = {"X-API-Key": key}
    assert client.post("/workers/claim", headers=new_headers).status_code == 200
    heartbeat_path = f"/workers/{attempt_id}/heartbeat"
    assert client.post(heartbeat_path, headers=old_headers).status_code == 401
    assert client.post(heartbeat_path, headers=new_headers).status_code == 200
    assert client.post(
        f"/workers/{attempt_id}/succeed", headers=new_headers, json={"result": {}},
    ).status_code == 200
    for path, expected in ((f"/workers/{worker_id}", created), ("/workers", [created])):
        response = client.get(path, headers=user_headers)
        assert response.status_code == 200
        assert response.json() == expected
        assert "secret_api_key" not in response.text
        assert hash_api_key(key) not in response.text
        assert key not in response.text


def test_reissuing_worker_key_does_not_reactivate_inactive_worker(
    client, database, claim_worker, user_headers
):
    worker, old_headers = claim_worker
    with Session(database) as session:
        session.get(Worker, worker.id).active = False
        session.commit()
    response = client.post(f"/workers/{worker.id}/api-key", headers=user_headers)
    assert response.status_code == 200
    key = response.json()["secret_api_key"]
    with Session(database) as session:
        stored = session.get(Worker, worker.id)
        assert stored.active is False
        assert stored.secret_api_key_hash == hash_api_key(key)
    for headers in (old_headers, {"X-API-Key": key}):
        assert client.post("/workers/claim", headers=headers).status_code == 401


@pytest.mark.parametrize("method, suffix, payload", [
    ("PUT", "/supported-types", {"supported_types": ["new"]}),
    ("POST", "/api-key", None),
    ("DELETE", "", None),
])
@pytest.mark.parametrize("access", [
    "anonymous", "worker-key", "PRIVATE", "PERMITTED_USERS", "ALL", "missing",
])
def test_worker_management_requires_owner_and_does_not_change_rejected_workers(
    client, database, user, user_headers, claim_worker, method, suffix, payload, access
):
    worker, worker_headers = claim_worker
    headers = user_headers
    worker_id = worker.id
    with Session(database) as session:
        stored = session.get(Worker, worker.id)
        if access in {"PRIVATE", "PERMITTED_USERS", "ALL"}:
            stored.user = User(
                username="other-owner", email="other@example.com",
                full_name="Other", hashed_password="unused",
            )
            stored.permission_policy = PermissionPolicy(access)
            stored.permitted_users = [session.get(User, user.id)]
        elif access == "missing":
            worker_id += 10000
        else:
            headers = {} if access == "anonymous" else worker_headers
        session.commit()
        original_owner = stored.user_id

    response = client.request(
        method, f"/workers/{worker_id}{suffix}", headers=headers, json=payload,
    )
    expected = 401 if access in {"anonymous", "worker-key"} else 404
    assert response.status_code == expected
    if expected == 404:
        assert response.json() == {"detail": "Worker not found"}
    with Session(database) as session:
        stored = session.get(Worker, worker.id)
        assert stored is not None
        assert stored.user_id == original_owner
        assert stored.secret_api_key_hash == worker.secret_api_key_hash
        assert {t.type_name for t in stored.supported_types} == {"example"}


def test_delete_worker_removes_registration_types_and_visibility_grants(
    client, database, user, user_headers, claim_worker
):
    worker, key_headers = claim_worker
    with Session(database) as session:
        session.get(Worker, worker.id).permitted_users = [session.get(User, user.id)]
        session.commit()
    response = client.delete(f"/workers/{worker.id}", headers=user_headers)
    assert response.status_code == 204
    assert response.content == b""
    with Session(database) as session:
        assert session.get(Worker, worker.id) is None
        assert session.scalar(select(SupportedJobType).where(
            SupportedJobType.worker_id == worker.id,
        )) is None
        assert session.scalar(select(WorkerPermittedUser).where(
            WorkerPermittedUser.worker_id == worker.id,
        )) is None
    assert client.get(f"/workers/{worker.id}", headers=user_headers).status_code == 404
    assert client.get("/workers", headers=user_headers).json() == []
    assert client.post("/workers/claim", headers=key_headers).status_code == 401
    assert client.delete(f"/workers/{worker.id}", headers=user_headers).status_code == 404


@pytest.mark.parametrize("reference", ["grant", "RUNNING", "SUCCEEDED", "FAILED", "LOST"])
def test_delete_referenced_worker_returns_conflict_and_rolls_back(
    client, database, user, user_headers, claim_worker, job_factory, reference
):
    worker, key_headers = claim_worker
    with Session(database) as session:
        stored = session.get(Worker, worker.id)
        stored.permitted_users = [session.get(User, user.id)]
        job = job_factory()
        if reference == "grant":
            job.permitted_workers = [stored]
        else:
            job.status = JobStatus.FAILED if reference == "LOST" else JobStatus(reference)
            job.attempts_count = 1
            session.add(JobAttempt(
                job=job, worker=stored, params={}, attempt_number=1,
                status=AttemptStatus(reference),
            ))
        session.add(job)
        session.commit()
        job_id = job.id

    response = client.delete(f"/workers/{worker.id}", headers=user_headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Worker is referenced by jobs or attempts"}
    with Session(database) as session:
        stored = session.get(Worker, worker.id)
        assert stored.secret_api_key_hash == worker.secret_api_key_hash
        assert {t.type_name for t in stored.supported_types} == {"example"}
        assert [u.id for u in stored.permitted_users] == [user.id]
        assert session.get(Job, job_id) is not None
        if reference == "grant":
            assert session.get(PermittedWorker, (worker.id, job_id)) is not None
        else:
            attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
            assert attempt.worker_id == worker.id
            assert attempt.status == AttemptStatus(reference)
    assert client.post("/workers/claim", headers=key_headers).status_code != 401
