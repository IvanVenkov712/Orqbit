"""Producer service and DTO coverage while its schema migration is pending."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dto.job import JobCreate
from dto.producer import ProducerAPIKeyResponse, ProducerCreate, ProducerCreateResponse
from models.job import Job, JobStatus, PermissionPolicy
from models.producers import Producer
from models.user import User
from services.api_key_auth import hash_api_key
from services.job import JobCreationConflict, get_request_fingerprint
from services.job import create_job as create_job_service
from services.producer import (
    ProducerCreationConflict,
    ProducerDeletionConflict,
    accessible_producers_query,
    create_producer,
    delete_producer,
    get_owned_producer,
    producer_accessible,
    producer_read_from_producer,
    reissue_producer_api_key,
)
from services.producer_auth import get_current_producer


@pytest.fixture
def producer():
    return Producer(
        id=10,
        name="test-producer",
        user=User(id=1, username="owner"),
        user_id=1,
        active=True,
        secret_api_key_hash=hash_api_key("old-key"),
    )


@pytest.mark.parametrize("name", ["", "ab", "x" * 17, "has spaces", "bad!"])
def test_producer_create_rejects_invalid_names(name):
    with pytest.raises(ValidationError):
        ProducerCreate(name=name)


def test_create_producer_hashes_key_and_returns_producer_fields(producer):
    session = Mock(spec=Session)

    def refresh(created):
        created.id = producer.id
        created.user_id = producer.user_id
        created.active = True

    session.refresh.side_effect = refresh
    response = create_producer(
        session, producer.user, ProducerCreate(name="new-producer")
    )

    created = session.add.call_args.args[0]
    assert isinstance(created, Producer)
    assert created.user is producer.user
    assert created.secret_api_key_hash == hash_api_key(response.secret_api_key)
    assert created.secret_api_key_hash != response.secret_api_key
    assert isinstance(response, ProducerCreateResponse)
    assert response.model_dump(exclude={"secret_api_key"}) == {
        "id": 10,
        "name": "new-producer",
        "active": True,
        "user_id": 1,
        "owner_username": "owner",
    }
    session.commit.assert_called_once()


@pytest.mark.parametrize("duplicate_name", [True, False])
def test_create_producer_rolls_back_and_only_translates_name_conflicts(
    producer, duplicate_name
):
    session = Mock(spec=Session)
    error = IntegrityError(None, None, UniqueViolation())
    session.commit.side_effect = error
    session.scalar.return_value = 20 if duplicate_name else None

    with pytest.raises(
        ProducerCreationConflict if duplicate_name else IntegrityError
    ) as raised:
        create_producer(session, producer.user, ProducerCreate(name=producer.name))

    session.rollback.assert_called_once()
    if not duplicate_name:
        assert raised.value is error


def test_owned_producer_lookup_filters_producer_and_owner_and_locks(producer):
    session = Mock(spec=Session)
    session.scalar.return_value = producer
    assert get_owned_producer(10, session, producer.user) is producer

    stmt = session.scalar.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert stmt.column_descriptions[0]["entity"] is Producer
    assert stmt.get_final_froms() == [Producer.__table__]
    assert "producers.id =" in str(compiled)
    assert "producers.user_id =" in str(compiled)
    assert set(compiled.params.values()) == {10, 1}
    assert "FOR UPDATE" in str(compiled)

    session.scalar.return_value = None
    assert get_owned_producer(999, session, producer.user) is None


def test_producer_visibility_is_owner_only(producer):
    other = User(id=2, username="other")
    assert producer_accessible(producer, producer.user)
    assert not producer_accessible(producer, other)

    stmt = accessible_producers_query(other)
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert stmt.column_descriptions[0]["entity"] is Producer
    assert "WHERE producers.user_id =" in str(compiled)
    assert list(compiled.params.values()) == [other.id]


def test_producer_read_excludes_credentials(producer):
    data = producer_read_from_producer(producer).model_dump()
    assert data == {
        "id": 10,
        "name": "test-producer",
        "active": True,
        "user_id": 1,
        "owner_username": "owner",
    }


def test_reissue_producer_key_replaces_hash_and_only_returns_key(producer):
    session = Mock(spec=Session)
    old_hash = producer.secret_api_key_hash
    response = reissue_producer_api_key(session, producer)

    assert isinstance(response, ProducerAPIKeyResponse)
    assert producer.secret_api_key_hash == hash_api_key(response.secret_api_key)
    assert producer.secret_api_key_hash != old_hash
    assert response.model_dump() == {"secret_api_key": response.secret_api_key}
    session.commit.assert_called_once()


@pytest.mark.parametrize("has_jobs", [True, False])
def test_delete_producer_preserves_published_jobs(producer, has_jobs):
    session = Mock(spec=Session)
    session.scalar.side_effect = [producer.id, 42 if has_jobs else None]

    if has_jobs:
        with pytest.raises(ProducerDeletionConflict, match="referenced by jobs"):
            delete_producer(session, producer)
        session.delete.assert_not_called()
        session.commit.assert_not_called()
    else:
        delete_producer(session, producer)
        session.delete.assert_called_once_with(producer)
        session.commit.assert_called_once()


@pytest.mark.parametrize("foreign_key", [True, False])
def test_delete_producer_rolls_back_and_only_translates_foreign_key_errors(
    producer, foreign_key
):
    session = Mock(spec=Session)
    session.scalar.side_effect = [producer.id, None]
    error = IntegrityError(
        None, None, ForeignKeyViolation() if foreign_key else NotNullViolation()
    )
    session.commit.side_effect = error

    with pytest.raises(
        ProducerDeletionConflict if foreign_key else IntegrityError
    ) as raised:
        delete_producer(session, producer)

    session.rollback.assert_called_once()
    if not foreign_key:
        assert raised.value is error


@pytest.fixture
def management_session():
    return Mock(spec=Session)


@pytest.fixture
def management_client(producer, management_session):
    from database import get_session
    from main import app
    from services.user_auth import get_current_active_user

    with (
        patch.dict(
            app.dependency_overrides,
            {
                get_session: lambda: management_session,
                get_current_active_user: lambda: producer.user,
            },
        ),
        TestClient(app) as client,
    ):
        yield client


def test_create_producer_endpoint(management_client, management_session, producer):
    def refresh(created):
        created.id = 20
        created.user_id = producer.user_id
        created.active = True

    management_session.refresh.side_effect = refresh
    response = management_client.post("/producers", json={"name": "new-producer"})

    assert response.status_code == 200
    data = response.json()
    created = management_session.add.call_args.args[0]
    assert created.user is producer.user
    assert created.secret_api_key_hash == hash_api_key(data.pop("secret_api_key"))
    assert data == {
        "id": 20,
        "name": "new-producer",
        "active": True,
        "user_id": 1,
        "owner_username": "owner",
    }
    management_session.commit.assert_called_once()


def test_create_producer_endpoint_conflict(management_client, management_session):
    management_session.commit.side_effect = IntegrityError(
        None, None, UniqueViolation()
    )
    management_session.scalar.return_value = 10
    response = management_client.post("/producers", json={"name": "test-producer"})
    assert response.status_code == 409
    assert response.json() == {"detail": "Producer name already exists"}
    management_session.rollback.assert_called_once()


@pytest.mark.parametrize("payload", [{}, {"name": "ab"}, {"name": "has spaces"}])
def test_create_producer_endpoint_rejects_invalid_input(
    management_client, management_session, payload
):
    response = management_client.post("/producers", json=payload)
    assert response.status_code == 422
    management_session.add.assert_not_called()
    management_session.commit.assert_not_called()


@pytest.mark.parametrize(
    "query, escaped",
    [
        (None, None),
        ("TeSt", "TeSt"),
        ("_", "/_"),
        ("%", "/%"),
        ("a/b", "a//b"),
    ],
)
def test_list_producers_scopes_search_and_omits_credentials(
    management_client, management_session, producer, query, escaped
):
    producer.active = False
    management_session.scalars.return_value.all.return_value = [producer]
    params = {"limit": 2, "offset": 1}
    if query is not None:
        params["query"] = query
    response = management_client.get("/producers", params=params)

    assert response.status_code == 200
    assert response.json() == [producer_read_from_producer(producer).model_dump()]
    stmt = management_session.scalars.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "WHERE producers.user_id =" in sql
    assert compiled.params["user_id_1"] == producer.user_id
    assert "ORDER BY producers.id DESC" in sql
    assert "LIMIT" in sql and "OFFSET" in sql
    assert compiled.params["param_1"] == 2
    assert compiled.params["param_2"] == 1
    if query is not None:
        assert "producers.name ILIKE" in sql
        assert "ESCAPE '/'" in sql
        assert compiled.params["name_1"] == escaped
    else:
        assert "ILIKE" not in sql


def test_list_producers_returns_empty_array(management_client, management_session):
    management_session.scalars.return_value.all.return_value = []
    response = management_client.get("/producers")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"query": ""},
        {"query": "x" * 17},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_list_producers_rejects_invalid_filters(
    management_client, management_session, params
):
    assert management_client.get("/producers", params=params).status_code == 422
    management_session.scalars.assert_not_called()


@pytest.mark.parametrize(
    "path, field, value",
    [
        ("/producers/10", "id", 10),
        ("/producers/by-name/test-producer", "name", "test-producer"),
        ("/producers/by-name/123", "name", "123"),
    ],
)
@pytest.mark.parametrize("active", [True, False])
def test_get_producer_returns_owned_metadata_without_credentials(
    management_client, management_session, producer, path, field, value, active
):
    producer.active = active
    if field == "name":
        producer.name = value
    management_session.scalar.return_value = producer
    response = management_client.get(path)

    assert response.status_code == 200
    assert response.json() == {
        "id": producer.id,
        "name": producer.name,
        "active": active,
        "user_id": producer.user_id,
        "owner_username": producer.user.username,
    }
    stmt = management_session.scalar.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "WHERE producers.user_id =" in sql
    assert compiled.params["user_id_1"] == producer.user_id
    assert f"producers.{field} =" in sql
    assert set(compiled.params.values()) == {producer.user_id, value}
    assert "LIKE" not in sql
    assert "FOR UPDATE" not in sql
    management_session.commit.assert_not_called()


@pytest.mark.parametrize(
    "path",
    [
        "/producers/not-an-id",
        "/producers/by-name/ab",
        "/producers/by-name/" + "x" * 17,
        "/producers/by-name/invalid!",
    ],
)
def test_get_producer_rejects_invalid_identifier(
    management_client, management_session, path
):
    response = management_client.get(path)
    assert response.status_code == 422
    management_session.scalar.assert_not_called()


@pytest.mark.parametrize("active", [True, False])
def test_reissue_producer_endpoint_preserves_active_state(
    management_client, management_session, producer, active
):
    producer.active = active
    old_hash = producer.secret_api_key_hash
    management_session.scalar.return_value = producer
    response = management_client.post("/producers/10/api-key")

    assert response.status_code == 200
    assert set(response.json()) == {"secret_api_key"}
    assert producer.secret_api_key_hash == hash_api_key(
        response.json()["secret_api_key"]
    )
    assert producer.secret_api_key_hash != old_hash
    assert producer.active is active
    management_session.commit.assert_called_once()


@pytest.mark.parametrize("active", [True, False])
def test_deactivate_producer_endpoint_preserves_key_and_rejects_authentication(
    management_client, management_session, producer, active
):
    producer.active = active
    old_hash = producer.secret_api_key_hash
    management_session.scalar.return_value = producer
    response = management_client.post("/producers/10/deactivate")

    assert response.status_code == 200
    assert response.json() == producer_read_from_producer(producer).model_dump()
    assert response.json()["active"] is False
    assert producer.secret_api_key_hash == old_hash
    management_session.commit.assert_called_once()
    management_session.delete.assert_not_called()
    with pytest.raises(HTTPException) as raised:
        get_current_producer("old-key", management_session)
    assert raised.value.status_code == 401


@pytest.mark.parametrize("has_jobs", [True, False])
def test_delete_producer_endpoint(
    management_client, management_session, producer, has_jobs
):
    management_session.scalar.side_effect = [
        producer,
        producer.id,
        42 if has_jobs else None,
    ]
    response = management_client.delete("/producers/10")

    if has_jobs:
        assert response.status_code == 409
        assert response.json() == {"detail": "Producer is referenced by jobs"}
        management_session.delete.assert_not_called()
        management_session.commit.assert_not_called()
    else:
        assert response.status_code == 204
        assert response.content == b""
        management_session.delete.assert_called_once_with(producer)
        management_session.commit.assert_called_once()


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/producers/10"),
        ("GET", "/producers/by-name/test-producer"),
        ("POST", "/producers/10/api-key"),
        ("POST", "/producers/10/deactivate"),
        ("DELETE", "/producers/10"),
    ],
)
def test_producer_management_missing_or_unowned_returns_404(
    management_client, management_session, producer, method, path
):
    management_session.scalar.return_value = None
    old_hash = producer.secret_api_key_hash
    response = management_client.request(method, path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Producer not found"}
    stmt = management_session.scalar.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "producers.user_id =" in str(compiled)
    assert compiled.params["user_id_1"] == producer.user_id
    assert producer.secret_api_key_hash == old_hash
    assert producer.active is True
    management_session.delete.assert_not_called()
    management_session.commit.assert_not_called()


@pytest.mark.parametrize(
    "method, path, payload",
    [
        ("POST", "/producers", {"name": "new-producer"}),
        ("GET", "/producers", None),
        ("GET", "/producers/10", None),
        ("GET", "/producers/by-name/test-producer", None),
        ("POST", "/producers/10/api-key", None),
        ("POST", "/producers/10/deactivate", None),
        ("DELETE", "/producers/10", None),
    ],
)
@pytest.mark.parametrize("credentials", ["anonymous", "api-key", "inactive-user"])
def test_producer_management_requires_active_user(
    management_client, management_session, producer, method, path, payload, credentials
):
    from main import app
    from services.user_auth import create_access_token, get_current_active_user

    del app.dependency_overrides[get_current_active_user]
    headers = {}
    if credentials == "api-key":
        headers["X-API-Key"] = "old-key"
    elif credentials == "inactive-user":
        producer.user.active = False
        management_session.scalar.return_value = producer.user
        headers["Authorization"] = (
            f"Bearer {create_access_token(producer.user.username)}"
        )

    response = management_client.request(method, path, headers=headers, json=payload)
    assert response.status_code == (403 if credentials == "inactive-user" else 401)
    management_session.add.assert_not_called()
    management_session.delete.assert_not_called()
    management_session.commit.assert_not_called()
    management_session.scalars.assert_not_called()


@pytest.fixture
def producer_job(producer):
    now = datetime(2026, 11, 12, tzinfo=UTC)
    payload = JobCreate(job_type="example", params={}, permission_policy="PRIVATE")
    return Job(
        id=100,
        user=producer.user,
        user_id=producer.user_id,
        producer=producer,
        producer_id=producer.id,
        job_type=payload.job_type,
        params=payload.params,
        permission_policy=PermissionPolicy.PRIVATE,
        status=JobStatus.PENDING,
        idempotency_key="submission",
        request_fingerprint=get_request_fingerprint(payload),
        max_attempts=1,
        attempts_count=0,
        available_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def producer_client(producer, management_session):
    from database import get_session
    from main import app

    with (
        patch.dict(
            app.dependency_overrides,
            {
                get_session: lambda: management_session,
                get_current_producer: lambda: producer,
            },
        ),
        TestClient(app) as client,
    ):
        yield client


def test_producer_creates_job_with_authenticated_ownership(
    producer_client, management_session, producer, producer_job
):
    def refresh(job):
        for field in (
            "id",
            "user_id",
            "producer_id",
            "status",
            "max_attempts",
            "attempts_count",
            "available_at",
            "created_at",
            "updated_at",
        ):
            setattr(job, field, getattr(producer_job, field))

    management_session.scalar.return_value = None
    management_session.scalars.return_value.all.return_value = []
    management_session.refresh.side_effect = refresh
    response = producer_client.post(
        "/producer/jobs",
        headers={"Idempotency-Key": "submission"},
        json={
            "job_type": "example",
            "params": {},
            "permission_policy": "PRIVATE",
            "producer_id": 999,
            "user_id": 999,
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == 100
    assert response.json()["user_id"] == producer.user_id
    assert response.json()["status"] == "PENDING"
    created = management_session.add.call_args.args[0]
    assert created.producer is producer
    assert created.user is producer.user
    assert created.idempotency_key == "submission"
    management_session.commit.assert_called_once()


@pytest.mark.parametrize("saved_producer_id", [10, 11, None])
@pytest.mark.parametrize("race", [False, True])
def test_producer_job_replays_never_return_other_submitters_jobs(
    producer_client, management_session, producer, producer_job, saved_producer_id, race
):
    producer_job.producer_id = saved_producer_id
    if race:
        management_session.scalar.side_effect = [None, producer_job]
        management_session.scalars.return_value.all.return_value = []
        management_session.commit.side_effect = IntegrityError(
            None, None, UniqueViolation()
        )
    else:
        management_session.scalar.return_value = producer_job
    response = producer_client.post(
        "/producer/jobs",
        headers={"Idempotency-Key": "submission"},
        json={"job_type": "example", "params": {}, "permission_policy": "PRIVATE"},
    )

    if saved_producer_id == producer.id:
        assert response.status_code == 200
        assert response.json()["id"] == producer_job.id
    else:
        assert response.status_code == 409
        assert response.json() == {"detail": "Conflicting create requests"}
    if race:
        management_session.rollback.assert_called_once()
    else:
        management_session.commit.assert_not_called()


def test_user_submission_cannot_replay_producer_job(
    management_session, producer, producer_job
):
    management_session.scalar.return_value = producer_job
    payload = JobCreate(job_type="example", params={}, permission_policy="PRIVATE")
    with pytest.raises(JobCreationConflict):
        create_job_service(management_session, producer.user, payload, "submission")


def test_producer_job_replay_rejects_changed_payload(
    producer_client, management_session, producer_job
):
    management_session.scalar.return_value = producer_job
    response = producer_client.post(
        "/producer/jobs",
        headers={"Idempotency-Key": "submission"},
        json={
            "job_type": "example",
            "params": {"changed": True},
            "permission_policy": "PRIVATE",
        },
    )
    assert response.status_code == 409
    management_session.commit.assert_not_called()


@pytest.mark.parametrize("key", [None, "", "   ", "x" * 101])
def test_producer_submission_requires_valid_idempotency_key(
    producer_client, management_session, key
):
    response = producer_client.post(
        "/producer/jobs",
        headers={} if key is None else {"Idempotency-Key": key},
        json={"job_type": "example", "params": {}, "permission_policy": "PRIVATE"},
    )
    assert response.status_code == 422
    management_session.add.assert_not_called()


@pytest.mark.parametrize("invalid", ["payload", "permission-ids"])
def test_producer_submission_rejects_invalid_payload_or_permissions(
    producer_client, management_session, invalid
):
    management_session.scalar.return_value = None
    management_session.scalars.return_value.all.return_value = []
    payload = {"job_type": "example", "params": {}, "permission_policy": "PRIVATE"}
    if invalid == "payload":
        payload["params"] = []
    else:
        payload["permitted_user_ids"] = [999]
    response = producer_client.post(
        "/producer/jobs", headers={"Idempotency-Key": "submission"}, json=payload
    )
    assert response.status_code == 422
    management_session.add.assert_not_called()
    management_session.commit.assert_not_called()


@pytest.mark.parametrize(
    "sort, order",
    [
        (None, "jobs.id DESC"),
        ("status_updated", "jobs.status, jobs.updated_at DESC, jobs.id DESC"),
        ("status_desc", "jobs.status DESC, jobs.updated_at DESC, jobs.id DESC"),
        ("created_asc", "jobs.created_at ASC, jobs.id DESC"),
        ("created_desc", "jobs.created_at DESC, jobs.id DESC"),
        ("updated_asc", "jobs.updated_at ASC, jobs.id DESC"),
        ("updated_desc", "jobs.updated_at DESC, jobs.id DESC"),
        ("type_asc", "jobs.job_type ASC, jobs.id DESC"),
        ("type_desc", "jobs.job_type DESC, jobs.id DESC"),
        ("owner_asc", "users.username ASC, jobs.id DESC"),
        ("owner_desc", "users.username DESC, jobs.id DESC"),
    ],
)
def test_producer_job_list_keeps_ownership_filters_sorting_and_summary(
    producer_client, management_session, producer, producer_job, sort, order
):
    management_session.scalars.return_value.all.return_value = [producer_job]
    params = {
        "owner_id": producer.user_id,
        "owner_username": producer.user.username,
        "status": "PENDING",
        "job_type": "example",
        "attempt_status": "LOST",
        "created_from": "2026-11-11T00:00:00Z",
        "created_before": "2026-11-13T00:00:00Z",
        "limit": 1,
        "offset": 2,
    }
    if sort is not None:
        params["sort"] = sort
    response = producer_client.get("/producer/jobs", params=params)

    assert response.status_code == 200
    assert response.json()[0]["id"] == producer_job.id
    assert set(response.json()[0]) == {
        "id",
        "user_id",
        "owner_username",
        "job_type",
        "status",
        "created_at",
        "updated_at",
    }
    stmt = management_session.scalars.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "WHERE jobs.producer_id =" in sql
    assert compiled.params["producer_id_1"] == producer.id
    assert " OR " not in sql
    assert "jobs.user_id =" in sql and "users.username =" in sql
    assert "jobs.status =" in sql and "jobs.job_type =" in sql
    assert "EXISTS" in sql and "job_attempts.status =" in sql
    assert "jobs.created_at >=" in sql and "jobs.created_at <" in sql
    assert sql.partition("ORDER BY ")[2].startswith(order)
    assert list(compiled.params.values())[-2:] == [1, 2]


@pytest.mark.parametrize(
    "params",
    [
        {"status": "INVALID"},
        {"attempt_status": "INVALID"},
        {"sort": "invalid"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"owner_username": ""},
        {"created_from": "invalid"},
        {"created_from": "2026-11-12T00:00:00"},
        {
            "created_from": "2026-11-13T00:00:00Z",
            "created_before": "2026-11-12T00:00:00Z",
        },
        {
            "created_from": "2026-11-12T00:00:00Z",
            "created_before": "2026-11-12T00:00:00Z",
        },
    ],
)
def test_producer_job_list_validates_filters(
    producer_client, management_session, params
):
    response = producer_client.get("/producer/jobs", params=params)
    assert response.status_code == 422
    management_session.scalars.assert_not_called()


def test_producer_job_list_empty(producer_client, management_session):
    management_session.scalars.return_value.all.return_value = []
    response = producer_client.get("/producer/jobs")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("found", [True, False])
def test_producer_job_by_id_is_scoped_to_authenticated_producer(
    producer_client, management_session, producer, producer_job, found
):
    management_session.scalar.return_value = producer_job if found else None
    response = producer_client.get("/producer/jobs/100")
    if found:
        assert response.status_code == 200
        assert response.json()["id"] == 100
        assert response.json()["params"] == {}
        assert response.json()["attempt_ids"] == []
    else:
        assert response.status_code == 404
        assert response.json() == {"detail": "Job not found"}
    stmt = management_session.scalar.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "WHERE jobs.producer_id =" in str(compiled)
    assert "jobs.id =" in str(compiled)
    assert compiled.params["producer_id_1"] == producer.id
    assert set(compiled.params.values()) == {producer.id, 100}
    assert " OR " not in str(compiled)


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/producer/jobs"),
        ("GET", "/producer/jobs"),
        ("GET", "/producer/jobs/100"),
    ],
)
@pytest.mark.parametrize("credentials", ["missing", "bearer", "invalid", "inactive"])
def test_producer_job_routes_require_active_producer_key(
    producer_client, management_session, producer, method, path, credentials
):
    from main import app

    del app.dependency_overrides[get_current_producer]
    headers = {"Idempotency-Key": "submission"}
    management_session.scalar.return_value = None
    if credentials == "bearer":
        headers["Authorization"] = "Bearer user-token"
    elif credentials in {"invalid", "inactive"}:
        headers["X-API-Key"] = "old-key"
        if credentials == "inactive":
            producer.active = False
            management_session.scalar.return_value = producer
    response = producer_client.request(
        method,
        path,
        headers=headers,
        json={"job_type": "example", "params": {}, "permission_policy": "PRIVATE"},
    )
    assert response.status_code == 401
    management_session.scalars.assert_not_called()
    management_session.add.assert_not_called()
    management_session.commit.assert_not_called()


def test_producer_job_route_authenticates_real_dependency(
    producer_client, management_session, producer, producer_job
):
    from main import app

    del app.dependency_overrides[get_current_producer]
    management_session.scalar.side_effect = [producer, producer_job]
    response = producer_client.get(
        "/producer/jobs/100", headers={"X-API-Key": "old-key"}
    )
    assert response.status_code == 200
    auth_stmt = management_session.scalar.call_args_list[0].args[0]
    compiled = auth_stmt.compile(dialect=postgresql.dialect())
    assert list(compiled.params.values()) == [hash_api_key("old-key")]
