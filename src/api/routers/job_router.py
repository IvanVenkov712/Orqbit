import fastapi
from fastapi import HTTPException
from sqlalchemy import select, or_, and_

from database import SessionDep
from dto.jobs import JobCreate, JobRead
from models.job import Job, JobStatus, PermissionPolicy
from models.user import User
from models.worker import Worker
from services.auth import CurrentUser

job_router = fastapi.APIRouter()

def accessible_jobs_query(user: User):
    return select(Job).where(
        or_(
            Job.user_id == user.id,

            Job.permission_policy == PermissionPolicy.ALL,

            and_(
                Job.permission_policy.in_([
                    PermissionPolicy.PERMITTED_USERS,
                    PermissionPolicy.PERMITTED_WORKERS_AND_USERS,
                ]),
                Job.permitted_users.any(User.id == user.id),
            ),
        )
    )

@job_router.post(path="/jobs/", response_model=JobRead)
def create_job(payload: JobCreate, session: SessionDep, user: CurrentUser):
    users = session.scalars(
        select(User).where(User.id.in_(payload.permitted_user_ids))
    ).all()

    workers = session.scalars(
        select(Worker).where(Worker.id.in_(payload.permitted_worker_ids))
    ).all()

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

@job_router.get(path="/jobs", response_model=list[JobRead])
def list_jobs(
        session: SessionDep,
        user: CurrentUser,
        owner: str | int | None = "me",
        status: JobStatus | None = None,
        job_type: str | None = None,
):
    stmt = select(Job)
    if owner == "me":
        stmt = stmt.where(
            Job.user_id == user.id
        )
    else:
        stmt = stmt.where(
            
        )
    return session.scalars(stmt).all()


@job_router.get(path="/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: SessionDep):
    job = session.get(Job, job_id)

    if job is None:
        raise HTTPException(404, "Job not found")

    return job



