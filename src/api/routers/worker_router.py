from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

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

def worker_read_from_worker(worker: Worker) -> WorkerRead:
    return WorkerRead(
        id=worker.id,
        name=worker.name,
        active=worker.active,
        user_id=worker.user_id,
        permission_policy=worker.permission_policy,
        supported_types=set(t.type_name for t in worker.supported_types),
        permitted_user_ids=[u.id for u in worker.permitted_users],
    )
    

@worker_router.post(path="/workers", response_model=WorkerCreateResponse)
def create_worker(payload: WorkerCreate, user: CurrentUser, session: SessionDep):
    users = session.scalars(
        select(User).where(User.id.in_(payload.permitted_user_ids))
    ).all()

    if len(users) != len(set(payload.permitted_user_ids)):
        raise HTTPException(
            status_code=422,
            detail="Some permitted users do not exist",
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

    return WorkerCreateResponse(
        id=worker.id,
        name=worker.name,
        active=worker.active,
        user_id=worker.user_id,
        permission_policy=worker.permission_policy,
        supported_types=set(t.type_name for t in worker.supported_types),
        permitted_user_ids=[u.id for u in worker.permitted_users],
        secret_api_key=api_key,
    )

@worker_router.get(path="/workers", response_model=list[WorkerRead])
def list_workers(
    user: CurrentUser,
    session: SessionDep,
    owner_id: int | None = None,
    job_type: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = accessible_workers_query(user)

    if owner_id is not None:
        stmt = stmt.where(Worker.user_id == owner_id)

    if job_type is not None:
        stmt = stmt.where(
            Worker.supported_types.any(SupportedJobType.type_name == job_type)
        )

    stmt = stmt.order_by(Worker.id.desc()).offset(offset).limit(limit)

    stmt = stmt.options(
        selectinload(Worker.supported_types),
        selectinload(Worker.permitted_users),
    )

    return [
        worker_read_from_worker(worker) for worker in session.scalars(stmt).all()
    ]

@worker_router.get(path="/workers/{worker_id}", response_model=WorkerRead)
def get_worker(worker_id: int, session: SessionDep, user: CurrentUser):
    worker = session.get(Worker, worker_id)

    if worker is None or not worker_accessible(worker, user):
        raise HTTPException(404, "Worker not found")

    return worker_read_from_worker(worker)
