from fastapi import APIRouter, HTTPException

from database import SessionDep
from dto.claims import CompleteJob, FailJob
from dto.job_attempt import JobAttemptRead
from services import job_execution
from services.worker_auth import CurrentWorker

claim_router = APIRouter()


@claim_router.post(path="/workers/claim", response_model=JobAttemptRead)
def claim_job(worker: CurrentWorker, session: SessionDep):
    try:
        attempt = job_execution.claim_job(session, worker)
    except job_execution.NoJobAvailable as exc:
        raise HTTPException(404, str(exc)) from None
    return {
        "id": attempt.id,
        "job_id": attempt.job_id,
        "job_type": attempt.job.job_type,
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
    try:
        job_execution.complete_job(session, worker, attempt_id, payload)
    except job_execution.AttemptNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except job_execution.OutcomeConflict as exc:
        raise HTTPException(409, str(exc)) from None
    return {"Status": "200 OK"}


@claim_router.post(path="/workers/{attempt_id}/fail", status_code=200)
def fail_job(
    attempt_id: int,
    payload: FailJob,
    session: SessionDep,
    worker: CurrentWorker,
):
    try:
        job_execution.fail_job(session, worker, attempt_id, payload)
    except job_execution.AttemptNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except job_execution.OutcomeConflict as exc:
        raise HTTPException(409, str(exc)) from None
    return {"Status": "200 OK"}
