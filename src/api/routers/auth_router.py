from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from starlette import status

from database import SessionDep
from dto.user import UserRead, UserRegister
from services.auth import Token, authenticate_user, create_access_token

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
def register(session: SessionDep, user: UserRegister):


