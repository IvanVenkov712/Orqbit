"""Registration, password authentication, and rejected bearer tokens."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from models.user import User
from services.user_auth import get_password_hash, verify_password


@pytest.fixture
def registration():
    return {
        "username": "auth-test",
        "email": "auth@example.com",
        "full_name": "Auth Test",
        "password": "Example1@",
    }


def test_registration_login_and_current_user(client, database, registration):
    response = client.post("/auth/register", json=registration)
    assert response.status_code == 200
    profile = response.json()
    assert profile == {
        "id": profile["id"],
        "username": registration["username"],
        "email": registration["email"],
        "full_name": registration["full_name"],
        "active": True,
        "role": "REGULAR",
    }
    with Session(database) as session:
        stored = session.get(User, profile["id"])
        assert stored.hashed_password != registration["password"]
        assert verify_password(registration["password"], stored.hashed_password)
        assert stored.hashed_password not in response.text
    assert registration["password"] not in response.text

    response = client.post("/auth/login", data=registration)
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]
    claims = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert claims["sub"] == registration["username"]
    assert claims["exp"] > datetime.now(UTC).timestamp()
    response = client.get("/users/me/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == profile


@pytest.mark.parametrize("field", ["username", "email"])
def test_duplicate_registration_does_not_insert_user(
    client, database, user, registration, field
):
    registration[field] = getattr(user, field)
    response = client.post("/auth/register", json=registration)
    assert response.status_code == 400
    assert response.json() == {
        "detail": f"User with {field} {registration[field]} already exists"
    }
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [("username", "a"), ("email", "invalid"), ("password", "weak")],
)
def test_invalid_registration_does_not_insert_user(
    client, database, registration, field, value
):
    registration[field] = value
    assert client.post("/auth/register", json=registration).status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("case", ["wrong-password", "unknown-user", "inactive-user"])
def test_login_rejects_invalid_credentials(client, database, user, case):
    with Session(database) as session:
        stored = session.get(User, user.id)
        stored.hashed_password = get_password_hash("Example1@")
        stored.active = case != "inactive-user"
        session.commit()
    response = client.post(
        "/auth/login",
        data={
            "username": "unknown-user" if case == "unknown-user" else user.username,
            "password": "Wrong1@" if case == "wrong-password" else "Example1@",
        },
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "case",
    [
        "expired",
        "wrong-signature",
        "missing-exp",
        "missing-sub",
        "empty-sub",
        "nonstring-sub",
        "unknown-user",
        "malformed",
    ],
)
def test_current_user_rejects_invalid_tokens(client, user, case):
    claims = {"sub": user.username, "exp": datetime.now(UTC) + timedelta(hours=1)}
    key = settings.secret_key
    if case == "expired":
        claims["exp"] = datetime.now(UTC) - timedelta(hours=1)
    elif case == "wrong-signature":
        key = "1" * 64
    elif case.startswith("missing-"):
        del claims[case.removeprefix("missing-")]
    elif case == "empty-sub":
        claims["sub"] = ""
    elif case == "nonstring-sub":
        claims["sub"] = 12
    elif case == "unknown-user":
        claims["sub"] = "unknown-user"
    token = jwt.encode(claims, key, algorithm=settings.algorithm)
    if case == "malformed":
        token = "invalid-token"
    response = client.get("/users/me/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
