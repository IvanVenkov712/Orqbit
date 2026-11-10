from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from database import SessionDep
from dto.user import UserPublicRead, UserRead
from models.user import User
from services.user_auth import CurrentUser

user_router = APIRouter()


@user_router.get("/users/me/", response_model=UserRead)
def read_users_me(current_user: CurrentUser):
    return current_user


@user_router.get("/users", response_model=list[UserPublicRead])
def list_users(
    session: SessionDep,
    current_user: CurrentUser,
    query: str | None = Query(None, min_length=1, max_length=16),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = select(User).where(User.active.is_(True))
    if query is not None:
        stmt = stmt.where(User.username.icontains(query, autoescape=True))
    stmt = stmt.order_by(User.id.desc()).offset(offset).limit(limit)
    return session.scalars(stmt).all()


@user_router.get("/users/{user_id}", response_model=UserPublicRead)
def get_user(user_id: int, session: SessionDep, current_user: CurrentUser):
    user = session.get(User, user_id)
    if user is None or not user.active:
        raise HTTPException(404, "User not found")
    return user
