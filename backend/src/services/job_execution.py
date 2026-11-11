"""Claim jobs and record worker-reported outcomes."""
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
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

def claim_job(session: Session, worker: Worker) -> JobAttempt:
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
        raise NoJobAvailable("No jobs were found")

    now = session.execute(select(func.clock_timestamp())).scalar_one()

    job.status = JobStatus.RUNNING
    attempt = JobAttempt(
        attempt_number=1,
        job=job,
        worker=worker,
        params=job.params,
        lease_expires_at=now + timedelta(seconds=settings.lease_seconds),
    )
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

def get_db_now(session: Session):
    return session.execute(select(func.clock_timestamp())).scalar_one()

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

    if attempt.status != AttemptStatus.RUNNING:
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

    if attempt.status != AttemptStatus.RUNNING:
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
    if attempt.status != AttemptStatus.RUNNING:
        raise AttemptNotRunning("The attempt is not running")

    now = validate_not_expired(session, attempt)
    
    attempt.lease_expires_at = max(
        now + timedelta(seconds=settings.lease_extension_seconds),
        attempt.lease_expires_at
    )
    session.commit()
    return attempt.lease_expires_at

def recover_expired_attempts(session: Session):
    """Recover one bounded batch, committing attempts and their jobs together."""
    now = get_db_now(session)
    expired_attempt_ids = session.scalars(
        select(JobAttempt.id)
        .where(
            JobAttempt.status == AttemptStatus.RUNNING,
            JobAttempt.lease_expires_at <= now,
        )
        .order_by(JobAttempt.id)
        .limit(settings.recovery_batch_size)
        .with_for_update()
    ).all()
    stmt = (
        update(JobAttempt)
        .where(
            JobAttempt.id.in_(expired_attempt_ids),
            JobAttempt.status == AttemptStatus.RUNNING,
            JobAttempt.lease_expires_at <= now,

        )
        .values(status=AttemptStatus.LOST)
    ).returning(JobAttempt.job_id)

    job_ids = session.scalars(stmt)

    stmt = (
        update(Job)
        .where(
            Job.id.in_(job_ids),
            Job.status == JobStatus.RUNNING
        )
        .values(status=JobStatus.FAILED)
    )
    session.execute(stmt)

    session.commit()


