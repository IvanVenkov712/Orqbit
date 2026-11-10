"""Authenticated user discovery exposes public profiles only."""

import pytest
from sqlalchemy.orm import Session

from models.user import User


@pytest.fixture
def directory_users(database, user):
    with Session(database, expire_on_commit=False) as session:
        users = [
            User(
                username=username,
                email=f"{username}@example.com",
                full_name=f"Name for {username}",
                hashed_password="private-password-hash",
                active=username != "inactive-alice",
            )
            for username in [
                "Alice",
                "malice",
                "ali_ce",
                "aliXce",
                "bob",
                "inactive-alice",
            ]
        ]
        session.add_all(users)
        session.commit()
        return {record.username: record for record in users}


def test_list_users_returns_only_active_public_profiles(
    client, user, user_headers, directory_users
):
    response = client.get("/users", headers=user_headers)

    assert response.status_code == 200
    expected = [user, *[record for record in directory_users.values() if record.active]]
    assert response.json() == [
        {"id": record.id, "username": record.username, "full_name": record.full_name}
        for record in sorted(expected, key=lambda record: record.id, reverse=True)
    ]


@pytest.mark.parametrize(
    ("query", "usernames"),
    [
        ("ALICE", ["malice", "Alice"]),
        ("ali_ce", ["ali_ce"]),
        ("%", []),
        ("\\", []),
        ("nobody", []),
    ],
)
def test_user_search_matches_literal_username_substrings(
    client, user_headers, directory_users, query, usernames
):
    response = client.get("/users", headers=user_headers, params={"query": query})

    assert response.status_code == 200
    assert [record["username"] for record in response.json()] == usernames


def test_user_search_filters_before_pagination(client, user_headers, directory_users):
    response = client.get(
        "/users", headers=user_headers, params={"query": "ali", "limit": 2, "offset": 1}
    )

    assert response.status_code == 200
    assert [record["id"] for record in response.json()] == [
        directory_users["ali_ce"].id,
        directory_users["malice"].id,
    ]
    response = client.get("/users", headers=user_headers, params={"offset": 100})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"query": ""},
        {"query": "a" * 17},
        {"query": "\x00"},
        {"limit": 0},
        {"limit": 101},
        {"limit": "invalid"},
        {"offset": -1},
        {"offset": "invalid"},
    ],
)
def test_user_search_rejects_invalid_parameters(client, user_headers, params):
    assert client.get("/users", headers=user_headers, params=params).status_code == 422


def test_get_user_returns_another_users_public_profile(
    client, user_headers, directory_users
):
    target = directory_users["Alice"]
    response = client.get(f"/users/{target.id}", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": target.id,
        "username": target.username,
        "full_name": target.full_name,
    }


@pytest.mark.parametrize("target", ["missing", "inactive"])
def test_missing_and_inactive_users_return_404(
    client, user_headers, directory_users, target
):
    user_id = 0 if target == "missing" else directory_users["inactive-alice"].id
    response = client.get(f"/users/{user_id}", headers=user_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


@pytest.mark.parametrize("user_id", ["invalid", 2**31, 2**63])
def test_get_user_rejects_invalid_ids(client, user_headers, user_id):
    assert client.get(f"/users/{user_id}", headers=user_headers).status_code == 422


@pytest.mark.parametrize("path", ["/users", "/users/1"])
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer invalid"}, {"X-API-Key": "worker-key"}],
)
def test_user_discovery_requires_user_authentication(client, path, headers):
    assert client.get(path, headers=headers).status_code == 401


@pytest.mark.parametrize("path", ["/users", "/users/1"])
def test_inactive_callers_cannot_discover_users(
    client, database, user, user_headers, path
):
    with Session(database) as session:
        session.get(User, user.id).active = False
        session.commit()

    assert client.get(path, headers=user_headers).status_code == 403


def test_current_user_route_keeps_its_private_profile(client, user, user_headers):
    response = client.get("/users/me/", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "active": user.active,
        "role": user.role.value,
    }
