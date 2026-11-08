from fastapi import APIRouter

from dto.user import UserRead
from services.user_auth import CurrentUser

user_router = APIRouter()

@user_router.get("/users/me/", response_model=UserRead)
def read_users_me(current_user: CurrentUser):
    return current_user
