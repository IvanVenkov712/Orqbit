import fastapi
from fastapi import HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import SessionDep
from dto.job import JobCreate, JobRead
from models.job import Job, JobStatus
from models.user import User
from models.worker import Worker
from services.job import accessible_user_jobs_query, job_accessible_for_user
from services.user_auth import CurrentUser

job_router = fastapi.APIRouter()

@job_router.post(path="/jobs/", response_model=JobRead)
def create_job(payload: JobCreate, session: SessionDep, user: CurrentUser):
    users = session.scalars(
        select(User).where(User.id.in_(payload.permitted_user_ids))
    ).all()

    workers = session.scalars(
        select(Worker).where(Worker.id.in_(payload.permitted_worker_ids))
    ).all()

    if len(users) != len(set(payload.permitted_user_ids)):
        raise HTTPException(422, "Some permitted users do not exist")
    if len(workers) != len(set(payload.permitted_worker_ids)):
        raise HTTPException(422, "Some permitted workers do not exist")

    job = Job(
        user=user,
        job_type=payload.job_type,
        params=payload.params,
        permission_policy=payload.permission_policy,
        permitted_users=list(users),
        permitted_workers=list(workers)
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job

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



