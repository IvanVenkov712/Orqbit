import re
from typing import Annotated

from email_validator import validate_email
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from starlette import status

from database import SessionDep
from dto.user import UserRead, UserRegister
from models.user import User
from services.auth import (
    Token,
    authenticate_user,
    create_access_token,
    get_password_hash,
    validate_user_not_exist,
)

auth_router = APIRouter()

@auth_router.post("/auth/login", response_model=Token)
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db_session: SessionDep,
):
    user = authenticate_user(
        db_session,
        form_data.username,
        form_data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(
        access_token=create_access_token(user.username)
    )

@auth_router.post("/auth/register", response_model=UserRead)
def register(session: SessionDep, payload: UserRegister):

    validate_user_not_exist(session, payload.username, payload.email)

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password)
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return user
