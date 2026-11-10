"""Job-type suggestions come only from visible workers' supported types."""

import pytest
from sqlalchemy.orm import Session

from models.user import User
from models.worker import PermissionPolicy, Worker


def test_job_types_are_distinct_sorted_and_bounded(
    client, user_headers, worker_factory
):
    names = [f"type_{index:02}" for index in range(12)]
    worker_factory(tuple(reversed(names)))
    worker_factory(tuple(names[:3]))

    response = client.get("/job-types", headers=user_headers)
    assert response.status_code == 200
    assert response.json() == names[:10]

    response = client.get("/job-types", headers=user_headers, params={"limit": 100})
    assert response.status_code == 200
    assert response.json() == names

    response = client.get(
        "/job-types", headers=user_headers, params={"query": "type_0", "limit": 3}
    )
    assert response.status_code == 200
    assert response.json() == names[:3]


@pytest.mark.parametrize(
    ("policy", "owned", "granted", "visible"),
    [
        (PermissionPolicy.PRIVATE, True, False, True),
        (PermissionPolicy.PERMITTED_USERS, True, False, True),
        (PermissionPolicy.ALL, True, False, True),
        (PermissionPolicy.PRIVATE, False, False, False),
        (PermissionPolicy.PRIVATE, False, True, False),
        (PermissionPolicy.PERMITTED_USERS, False, False, False),
        (PermissionPolicy.PERMITTED_USERS, False, True, True),
        (PermissionPolicy.ALL, False, False, True),
    ],
)
def test_job_types_follow_worker_visibility(
    client,
    database,
    user,
    user_headers,
    worker_factory,
    policy,
    owned,
    granted,
    visible,
):
    worker, _ = worker_factory(("shared_type",))
    with Session(database) as session:
        stored = session.get(Worker, worker.id)
        stored.name = "visible-worker"
        if not owned:
            stored.user = User(
                username="other-owner",
                email="other@example.com",
                full_name="Other owner",
                hashed_password="unused",
            )
        stored.permission_policy = policy
        stored.permitted_users = [session.get(User, user.id)] if granted else []
        session.commit()

    response = client.get(
        "/job-types", headers=user_headers, params={"query": "shared", "limit": 1}
    )
    assert response.status_code == 200
    assert response.json() == (["shared_type"] if visible else [])
    assert client.get(f"/workers/{worker.id}", headers=user_headers).status_code == (
        200 if visible else 404
    )


def test_hidden_types_do_not_consume_the_result_limit(
    client, database, user_headers, worker_factory
):
    hidden, _ = worker_factory(("aaa_hidden",))
    worker_factory(("zzz_visible",))
    with Session(database) as session:
        stored = session.get(Worker, hidden.id)
        stored.user = User(
            username="hidden-owner",
            email="hidden@example.com",
            full_name="Hidden owner",
            hashed_password="unused",
        )
        stored.permission_policy = PermissionPolicy.PRIVATE
        session.commit()

    response = client.get("/job-types", headers=user_headers, params={"limit": 1})
    assert response.status_code == 200
    assert response.json() == ["zzz_visible"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("ADD", ["add_numbers", "addXnumbers"]),
        ("add_numbers", ["add_numbers"]),
        ("%", ["100%done"]),
        ("\\", ["path\\name"]),
        ("mixed_type", [" Mixed_Type "]),
        ("missing", []),
    ],
)
def test_job_type_search_matches_literal_case_insensitive_substrings(
    client, user_headers, worker_factory, query, expected
):
    worker_factory(
        ("add_numbers", "addXnumbers", "100%done", "path\\name", " Mixed_Type ")
    )

    response = client.get("/job-types", headers=user_headers, params={"query": query})
    assert response.status_code == 200
    assert sorted(response.json()) == sorted(expected)


def test_job_types_include_visible_inactive_registrations(
    client, database, user_headers, worker_factory
):
    worker, _ = worker_factory(("registered_type",))
    with Session(database) as session:
        session.get(Worker, worker.id).active = False
        session.commit()

    response = client.get("/job-types", headers=user_headers)
    assert response.status_code == 200
    assert response.json() == ["registered_type"]


def test_job_types_return_empty_when_no_workers_exist(client, user_headers):
    response = client.get("/job-types", headers=user_headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"query": ""},
        {"query": "a" * 101},
        {"query": "\x00"},
        {"limit": 0},
        {"limit": 101},
        {"limit": "invalid"},
    ],
)
def test_job_types_reject_invalid_parameters(client, user_headers, params):
    response = client.get("/job-types", headers=user_headers, params=params)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer invalid"}, {"X-API-Key": "worker-key"}],
)
def test_job_types_require_user_authentication(client, headers):
    assert client.get("/job-types", headers=headers).status_code == 401


def test_inactive_users_cannot_read_job_types(client, database, user, user_headers):
    with Session(database) as session:
        session.get(User, user.id).active = False
        session.commit()

    assert client.get("/job-types", headers=user_headers).status_code == 403
