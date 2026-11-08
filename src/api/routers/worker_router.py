from fastapi import APIRouter
from sqlalchemy import and_, or_, select

from models.user import User
from models.worker import PermissionPolicy, Worker

worker_router = APIRouter()

def accessible_workers_query(user: User):
    return select(Worker).where(
        or_(
            Worker.user_id == user.id,
            Worker.permission_policy == PermissionPolicy.ALL,
            and_(
                Worker.permission_policy == PermissionPolicy.PERMITTED_USERS,
                Worker.permitted_users.any(User.id == user.id),
            ),
        )
    )

def worker_accessible(worker: Worker, user: User) -> bool:

    if worker.permission_policy == PermissionPolicy.ALL:
        return True

    if worker.user_id == user.id:
        return True

    if worker.permission_policy == PermissionPolicy.PERMITTED_USERS:
        return any(p_user.id == user.id for p_user in worker.permitted_users)

    return False