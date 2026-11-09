from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dto.worker import WorkerCreate, WorkerCreateResponse, WorkerRead
from models.supported_types import SupportedJobType
from models.user import User
from models.worker import PermissionPolicy, Worker
from services.worker_auth import generate_api_key, hash_api_key


class WorkerCreationConflict(Exception):
    pass


class InvalidWorkerPermissions(Exception):
    pass


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


def create_worker(
    session: Session, user: User, payload: WorkerCreate
) -> WorkerCreateResponse:
    users = session.scalars(
        select(User).where(User.id.in_(payload.permitted_user_ids))
    ).all()

    if len(users) != len(set(payload.permitted_user_ids)):
        raise InvalidWorkerPermissions("Some permitted users do not exist")

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
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing_id = session.scalar(
            select(Worker.id).where(Worker.name == payload.name)
        )
        if existing_id is not None:
            raise WorkerCreationConflict("Worker name already exists") from None
        raise
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
