from http import HTTPStatus

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from database import SessionDep
from dto.claims import CompleteJob, FailJob
from dto.job_attempt import JobAttemptRead
from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt
from models.supported_types import SupportedJobType
from services.job import accessible_worker_jobs
from services.worker_auth import CurrentWorker

claim_router = APIRouter()


@claim_router.post(path="/workers/claim", response_model=JobAttemptRead)
def claim_job(worker: CurrentWorker, session: SessionDep):
    stmt = (
        accessible_worker_jobs(worker)
        .where(
            Job.status == JobStatus.PENDING,
            Job.job_type.in_(
                select(SupportedJobType.type_name).where(
                    SupportedJobType.worker_id == worker.id
                )
            ),
        )
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
    return {
        "id": attempt.id,
        "job_id": job.id,
        "job_type": job.job_type,
        "attempt_number": attempt.attempt_number,
        "status": attempt.status,
        "params": attempt.params,
    }

@claim_router.post(path="/workers/{attempt_id}/succeed", status_code=200)
def complete_job(
    attempt_id: int,
    payload: CompleteJob,
    session: SessionDep,
    worker: CurrentWorker,
):
    attempt = session.scalar(
        select(JobAttempt).where(JobAttempt.id == attempt_id).with_for_update()
    )
    if attempt is None or attempt.worker_id != worker.id:
        raise HTTPException(404, "Attempt not found")

    if attempt.status != AttemptStatus.RUNNING:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Job not running")


    attempt.status = AttemptStatus.SUCCEEDED
    attempt.result = payload.result

    job = attempt.job
    job.status = JobStatus.SUCCEEDED
    job.result = payload.result
    session.commit()
    return {
        "Status": "200 OK"
    }

@claim_router.post(path="/workers/{attempt_id}/fail", status_code=200)
def fail_job(
    attempt_id: int,
    payload: FailJob,
    session: SessionDep,
    worker: CurrentWorker,
):
    attempt = session.scalar(
        select(JobAttempt).where(JobAttempt.id == attempt_id).with_for_update()
    )
    if attempt is None or attempt.worker_id != worker.id:
        raise HTTPException(404, "Attempt not found")

    if attempt.status != AttemptStatus.RUNNING:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Attempt not running")

    attempt.status = AttemptStatus.FAILED
    attempt.error = payload.error

    job = attempt.job
    job.status = JobStatus.FAILED
    job.error = payload.error
    session.commit()
    return {"Status": "200 OK"}


