from http import HTTPStatus

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.dto.claims import ClaimJob, CompleteJob, FailJob
from api.dto.jobs import JobRead
from database import SessionDep
from models.job import Job, JobStatus

claim_router = APIRouter()

@claim_router.post(path="/workers/claim", response_model=JobRead)
def claim_job(payload: ClaimJob, session: SessionDep):
    stmt = (
        select(Job).where(
            Job.job_type.in_(payload.supported_types),
            Job.status == JobStatus.PENDING
        )
        .order_by(Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    job = session.scalars(stmt).first()

    if job is None:
        raise HTTPException(404, "No jobs were found")

    job.status = JobStatus.RUNNING
    session.commit()
    return job

@claim_router.post(path="/workers/{job_id}/succeed", status_code=200)
def complete_job(job_id: int, payload: CompleteJob, session: SessionDep):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    if job.status != JobStatus.RUNNING:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Job not running")

    job.status = JobStatus.SUCCEEDED
    job.result = payload.result
    session.commit()
    return {}

@claim_router.post(path="/workers/{job_id}/fail", status_code=200)
def fail_job(job_id: int, payload: FailJob, session: SessionDep):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    if job.status != JobStatus.RUNNING:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Job not running")

    job.status = JobStatus.FAILED
    job.error = payload.error
    session.commit()
    return {}


