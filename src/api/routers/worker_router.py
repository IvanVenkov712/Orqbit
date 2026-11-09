from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import selectinload

from database import SessionDep
from dto.worker import WorkerCreate, WorkerCreateResponse, WorkerRead
from models.supported_types import SupportedJobType
from models.worker import Worker
from services.user_auth import CurrentUser
from services.worker import (
    InvalidWorkerPermissions,
    WorkerCreationConflict,
    accessible_workers_query,
    worker_accessible,
    worker_read_from_worker,
)
from services.worker import create_worker as create_worker_service

worker_router = APIRouter()


@worker_router.post(path="/workers", response_model=WorkerCreateResponse)
def create_worker(payload: WorkerCreate, user: CurrentUser, session: SessionDep):
    try:
        return create_worker_service(session, user, payload)
    except WorkerCreationConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except InvalidWorkerPermissions as exc:
        raise HTTPException(422, str(exc)) from None


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

    return [worker_read_from_worker(worker) for worker in session.scalars(stmt).all()]


@worker_router.get(path="/workers/{worker_id}", response_model=WorkerRead)
def get_worker(worker_id: int, session: SessionDep, user: CurrentUser):
    worker = session.get(Worker, worker_id)

    if worker is None or not worker_accessible(worker, user):
        raise HTTPException(404, "Worker not found")

    return worker_read_from_worker(worker)
