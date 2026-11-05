import fastapi
from fastapi import HTTPException
from sqlalchemy import select

from api.dto.jobs import JobCreate, JobRead
from database import SessionDep
from models.job import Job

job_router = fastapi.APIRouter()


@job_router.post(path="/jobs/", response_model=JobRead)
def create_job(payload: JobCreate, session: SessionDep):
    job = Job(
        job_type=payload.job_type,
        params=payload.params
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job

@job_router.get(path="/jobs", response_model=list[JobRead])
def list_jobs(session: SessionDep):
    stmt = select(Job).order_by(Job.id)
    return session.scalars(stmt).all()


@job_router.get(path="/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: SessionDep):
    job = session.get(Job, job_id)

    if job is None:
        raise HTTPException(404, "Job not found")

    return job



