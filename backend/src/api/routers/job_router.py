from typing import Annotated, Literal

import fastapi
from fastapi import Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import load_only

import services
from database import SessionDep
from dto.job import JobCreate, JobRead, JobSummaryRead
from dto.job_attempt import JobAttemptRead
from models import JobAttempt
from models.job import Job, JobStatus
from services.job import (
    InvalidJobPermissions,
    JobCreationConflict,
    accessible_user_jobs_query,
)
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
        return services.job.create_job(session, user, payload, idempotency_key)
    except JobCreationConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except InvalidJobPermissions as exc:
        raise HTTPException(422, str(exc)) from None

@job_router.get("/jobs", response_model=list[JobSummaryRead])
def list_jobs(
    session: SessionDep,
    user: CurrentUser,
    owner_id: int | None = None,
    status: JobStatus | None = None,
    job_type: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: Literal["status_updated"] | None = None,
):
    stmt = accessible_user_jobs_query(user).options(
        load_only(
            Job.id,
            Job.user_id,
            Job.job_type,
            Job.status,
            Job.created_at,
            Job.updated_at,
        )
    )

    if owner_id is not None:
        stmt = stmt.where(Job.user_id == owner_id)

    if status is not None:
        stmt = stmt.where(Job.status == status)

    if job_type is not None:
        stmt = stmt.where(Job.job_type == job_type)

    if sort == "status_updated":
        stmt = stmt.order_by(Job.status, Job.updated_at.desc(), Job.id.desc())
    else:
        stmt = stmt.order_by(Job.id.desc())

    stmt = stmt.offset(offset).limit(limit)

    return session.scalars(stmt).all()


@job_router.get(path="/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: SessionDep, user: CurrentUser):
    job = services.job.get_job(job_id, session, user)

    if job is None:
        raise HTTPException(404, "Job not found")

    return job

@job_router.get(path="/jobs/{job_id}/attempts", response_model=list[JobAttemptRead])
def get_job_attempts(
    job_id: int,
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    job = services.job.get_job(job_id, session, user)

    if job is None:
        raise HTTPException(404, "Job not found")

    stmt = (
        select(JobAttempt)
        .where(JobAttempt.job_id == job.id)
        .order_by(JobAttempt.attempt_number.desc())
        .offset(offset)
        .limit(limit)
    )
    return session.scalars(stmt).all()




