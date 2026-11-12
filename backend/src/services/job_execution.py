"""Claim jobs and record worker-reported outcomes."""
from datetime import datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from config import settings
from dto.claims import CompleteJob, FailJob
from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt
from models.supported_types import SupportedJobType
from models.worker import Worker
from services.job import accessible_worker_jobs


class NoJobAvailable(Exception):
    pass


class AttemptNotFound(Exception):
    pass


class OutcomeConflict(Exception):
    pass


class AttemptNotRunning(Exception):
    pass


class LeaseExpired(Exception):
    pass


def claimable_jobs_query(worker: Worker) -> Select[tuple[Job]]:
    return (
        accessible_worker_jobs(worker)
        .where(
            Job.status == JobStatus.PENDING,
            Job.available_at <= func.clock_timestamp(),
            Job.attempts_count < Job.max_attempts,
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


def attempt_from_job(job: Job, worker: Worker, now: datetime) -> JobAttempt:
    """Start the next attempt while the caller holds the job row lock."""
    job.attempts_count += 1
    job.status = JobStatus.RUNNING
    return JobAttempt(
        attempt_number=job.attempts_count,
        job=job,
        worker=worker,
        params=job.params,
        lease_expires_at=now + timedelta(seconds=settings.lease_seconds),
    )


def claim_job(session: Session, worker: Worker) -> JobAttempt:
    job = session.scalars(claimable_jobs_query(worker)).first()
    if job is None:
        raise NoJobAvailable("No jobs were found")

    attempt = attempt_from_job(job, worker, get_db_now(session))
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def get_attempt(
        session: Session, worker: Worker, attempt_id: int,
) -> JobAttempt:
    attempt = session.scalar(
        select(JobAttempt).where(JobAttempt.id == attempt_id).with_for_update()
    )
    if attempt is None or attempt.worker_id != worker.id:
        raise AttemptNotFound("Attempt not found")

    return attempt

def get_db_now(session: Session) -> datetime:
    return session.execute(select(func.clock_timestamp())).scalar_one()


def is_current_attempt(attempt: JobAttempt) -> bool:
    job = attempt.job
    return (
        job.status == JobStatus.RUNNING
        and attempt.attempt_number == job.attempts_count
        and job.attempts_count <= job.max_attempts
    )


def validate_not_expired(
        session: Session,
        attempt: JobAttempt,
):
    now = get_db_now(session)

    if attempt.lease_expires_at <= now:
        raise LeaseExpired("The lease has expired")

    return now


def complete_job(
        session: Session, worker: Worker, attempt_id: int, payload: CompleteJob
) -> None:
    attempt = get_attempt(session, worker, attempt_id)

    if attempt.status == AttemptStatus.SUCCEEDED and session.scalar(
            select(JobAttempt.result == payload.result).where(JobAttempt.id == attempt_id)
    ):
        return

    if attempt.status != AttemptStatus.RUNNING or not is_current_attempt(attempt):
        raise OutcomeConflict("Conflicting outcome report")

    validate_not_expired(session, attempt)

    attempt.status = AttemptStatus.SUCCEEDED
    attempt.result = payload.result
    job = attempt.job
    job.status = JobStatus.SUCCEEDED
    job.result = payload.result
    session.commit()


def fail_job(
        session: Session, worker: Worker, attempt_id: int, payload: FailJob
) -> None:
    attempt = get_attempt(session, worker, attempt_id)

    if attempt.status == AttemptStatus.FAILED and session.scalar(
            select(JobAttempt.error == payload.error).where(JobAttempt.id == attempt_id)
    ):
        return

    if attempt.status != AttemptStatus.RUNNING or not is_current_attempt(attempt):
        raise OutcomeConflict("Conflicting outcome report")

    validate_not_expired(session, attempt)

    attempt.status = AttemptStatus.FAILED
    attempt.error = payload.error
    job = attempt.job
    job.status = JobStatus.FAILED
    job.error = payload.error
    session.commit()


def send_heartbeat(
        attempt_id: int, session: Session, worker: Worker
) -> datetime:
    attempt = get_attempt(session, worker, attempt_id)
    if attempt.status != AttemptStatus.RUNNING or not is_current_attempt(attempt):
        raise AttemptNotRunning("The attempt is not running")

    now = validate_not_expired(session, attempt)
    
    attempt.lease_expires_at = max(
        now + timedelta(seconds=settings.lease_extension_seconds),
        attempt.lease_expires_at
    )
    session.commit()
    return attempt.lease_expires_at


def retry_backoff(attempt_number: int) -> timedelta:
    return timedelta(seconds=min(10 * 2 ** (attempt_number - 1), 60))


def retry_available_at(now: datetime, attempt_number: int) -> datetime:
    return now + retry_backoff(attempt_number)


def schedule_retry(job: Job, now: datetime) -> None:
    if job.attempts_count < job.max_attempts:
        job.status = JobStatus.PENDING
        job.available_at = retry_available_at(now, job.attempts_count)
    else:
        job.status = JobStatus.FAILED
        job.error = {
            "code": "attempts_exhausted",
            "message": "Maximum attempts reached after lease expiry",
        }


def recover_expired_attempts(session: Session) -> None:
    """Recover one bounded batch, committing attempts and their jobs together."""
    now = get_db_now(session)
    expired_attempts = session.scalars(
        select(JobAttempt)
        .where(
            JobAttempt.status == AttemptStatus.RUNNING,
            JobAttempt.lease_expires_at <= now,
        )
        .order_by(JobAttempt.id)
        .limit(settings.recovery_batch_size)
        .with_for_update()
    ).all()
    attempt_numbers: dict[int, int] = {}
    for attempt in expired_attempts:
        attempt.status = AttemptStatus.LOST
        attempt_numbers[attempt.job_id] = attempt.attempt_number

    # Flush LOST before making jobs claimable; keep both changes atomic.
    session.flush()
    jobs = session.scalars(
        select(Job)
        .where(
            Job.id.in_(attempt_numbers),
            Job.status == JobStatus.RUNNING,
        )
        .order_by(Job.id)
        .with_for_update()
    )
    for job in jobs:
        if job.attempts_count == attempt_numbers[job.id]:
            schedule_retry(job, now)

    session.commit()


