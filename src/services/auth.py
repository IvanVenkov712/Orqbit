from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import SessionDep
from models.user import User

app = FastAPI()
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


# Response schemas

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Password utilities

def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


# User lookup and authentication

def get_user(session: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return session.scalar(stmt)


def authenticate_user(
        session: Session,
        username: str,
        password: str,
) -> User | None:
    user = get_user(session, username)

    if user is None:
        verify_password(password, DUMMY_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if not user.active:
        return None

    return user


# JWT utilities

def create_access_token(username: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )

    payload = {
        "sub": username,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.algorithm,
    )


# Authentication dependencies

def get_current_user(
        db_session: SessionDep,
        token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]},
        )

        username = payload.get("sub")

        if not isinstance(username, str) or not username:
            raise credentials_exception

    except InvalidTokenError as exc:
        raise credentials_exception from exc

    user = get_user(db_session, username)

    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(
        current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return current_user


CurrentUser = Annotated[User, Depends(get_current_active_user)]


def validate_user_not_exist(session: Session, username: str, email: str):
    stmt = select(User).where(User.username == username)
    user = session.scalar(stmt)
    if user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with username {username} already exists",
        )

    stmt = select(User).where(User.email == email)
    user = session.scalar(stmt)
    if user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email {email} already exists",
        )
