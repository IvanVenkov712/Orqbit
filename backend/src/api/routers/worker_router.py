from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from database import SessionDep
from dto.worker import WorkerCreate, WorkerCreateResponse, WorkerRead
from models.supported_types import SupportedJobType
from models.user import User
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


@worker_router.get("/job-types", response_model=list[str])
def list_job_types(
    user: CurrentUser,
    session: SessionDep,
    query: str | None = Query(None, min_length=1, max_length=100),
    limit: int = Query(10, ge=1, le=100),
):
    visible_worker_ids = accessible_workers_query(user).with_only_columns(Worker.id)
    stmt = select(SupportedJobType.type_name).where(
        SupportedJobType.worker_id.in_(visible_worker_ids)
    )
    if query is not None:
        stmt = stmt.where(SupportedJobType.type_name.icontains(query, autoescape=True))
    stmt = stmt.distinct().order_by(SupportedJobType.type_name).limit(limit)
    return session.scalars(stmt).all()


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
    owner_username: str | None = Query(None, min_length=1, max_length=16),
    job_type: str | None = None,
    active: bool | None = None,
    created_from: AwareDatetime | None = None,
    created_before: AwareDatetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if created_from is not None and created_before is not None and created_from >= created_before:
        raise HTTPException(422, "created_from must be earlier than created_before")
    stmt = accessible_workers_query(user)

    if owner_id is not None:
        stmt = stmt.where(Worker.user_id == owner_id)

    if owner_username is not None:
        stmt = stmt.where(Worker.user.has(User.username == owner_username))

    if job_type is not None:
        stmt = stmt.where(
            Worker.supported_types.any(SupportedJobType.type_name == job_type)
        )

    if active is not None:
        stmt = stmt.where(Worker.active == active)

    if created_from is not None:
        stmt = stmt.where(Worker.created_at >= created_from)

    if created_before is not None:
        stmt = stmt.where(Worker.created_at < created_before)

    stmt = stmt.order_by(Worker.id.desc()).offset(offset).limit(limit)

    stmt = stmt.options(
        joinedload(Worker.user).load_only(User.username),
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
