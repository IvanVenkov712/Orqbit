from fastapi import APIRouter
from sqlalchemy import and_, or_, select

from database import SessionDep
from dto.worker import WorkerCreate, WorkerCreateResponse, WorkerRead
from models.supported_types import SupportedJobType
from models.user import User
from models.worker import PermissionPolicy, Worker
from services.user_auth import CurrentUser
from services.worker_auth import generate_api_key, hash_api_key

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

@worker_router.post(path="/workers", response_model=WorkerCreateResponse)
def create_worker(payload: WorkerCreate, user: CurrentUser, session: SessionDep):
    users = session.scalars(
        select(User).where(User.id.in_(payload.permitted_user_ids))
    )
    api_key = generate_api_key()
    worker = Worker(
        name=payload.name,
        user=user,
        permission_policy=payload.permission_policy,
        permitted_users=list(users),
        supported_types=[
            SupportedJobType(type_name=job_type)
            for job_type in set(payload.supported_types)
        ],
        secret_api_key_hash=hash_api_key(api_key),
    )

    session.add(worker)
    session.commit()
    session.refresh(worker)

    response = 

    return worker