from typing import Annotated

import fastapi
from fastapi import Header, HTTPException, Query
from sqlalchemy.orm import selectinload

from database import SessionDep
from dto.job import JobCreate, JobRead
from models.job import Job, JobStatus
from services.job import (
    InvalidJobPermissions,
    JobCreationConflict,
    accessible_user_jobs_query,
    job_accessible_for_user,
)
from services.job import create_job as create_job_service
from services.user_auth import CurrentUser

job_router = fastapi.APIRouter()


@job_router.post(path="/jobs/", response_model=JobRead)
def create_job(
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=100, pattern=r"\S"),
    ],
    payload: JobCreate,
    session: SessionDep,
    user: CurrentUser,
):
    try:
        return create_job_service(session, user, payload, idempotency_key)
    except JobCreationConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except InvalidJobPermissions as exc:
        raise HTTPException(422, str(exc)) from None

@job_router.get("/jobs", response_model=list[JobRead])
def list_jobs(
    session: SessionDep,
    user: CurrentUser,
    owner_id: int | None = None,
    status: JobStatus | None = None,
    job_type: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = accessible_user_jobs_query(user).options(selectinload(Job.attempts))

    if owner_id is not None:
        stmt = stmt.where(Job.user_id == owner_id)

    if status is not None:
        stmt = stmt.where(Job.status == status)

    if job_type is not None:
        stmt = stmt.where(Job.job_type == job_type)

    stmt = (
        stmt
        .order_by(Job.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return session.scalars(stmt).all()


@job_router.get(path="/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: SessionDep, user: CurrentUser):
    job = session.get(Job, job_id)

    if job is None or not job_accessible_for_user(job, user):
        raise HTTPException(404, "Job not found")

    return job



