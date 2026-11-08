from http import HTTPStatus

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from database import SessionDep
from dto.claims import ClaimJob, CompleteJob, FailJob
from dto.job import JobRead
from dto.job_attempt import JobAttemptRead
from models.job import Job, JobStatus
from models.job_attempts import JobAttempt
from services.job import accessible_worker_jobs
from services.worker_auth import CurrentWorker

claim_router = APIRouter()

@claim_router.post(path="/workers/claim", response_model=JobAttemptRead)
def claim_job(payload: ClaimJob, worker: CurrentWorker, session: SessionDep):
    stmt = (
        accessible_worker_jobs(worker)
        .where(Job.job_type.in_(payload.supported_types))
        .order_by(Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    job = session.scalars(stmt).first()

    if job is None:
        raise HTTPException(404, "No jobs were found")

    job.status = JobStatus.RUNNING
    attempt = JobAttempt(
        attempt_number=1,
        job=job,
        worker=worker,
        params=job.params,
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt

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


