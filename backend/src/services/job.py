import hashlib
import json

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionDep
from dto.job import JobCreate
from models.job import Job, PermissionPolicy
from models.user import User
from models.worker import Worker
from services.user_auth import CurrentUser


class JobCreationConflict(Exception):
    pass


class InvalidJobPermissions(Exception):
    pass


def get_permitted_users(payload: JobCreate, session: Session) -> list[User]:
    users = session.scalars(
        select(User).where(User.id.in_(payload.permitted_user_ids))
    ).all()
    if len(users) != len(set(payload.permitted_user_ids)):
        raise InvalidJobPermissions("Some permitted users do not exist")
    return list(users)


def get_permitted_workers(payload: JobCreate, session: Session) -> list[Worker]:
    workers = session.scalars(
        select(Worker).where(Worker.id.in_(payload.permitted_worker_ids))
    ).all()
    if len(workers) != len(set(payload.permitted_worker_ids)):
        raise InvalidJobPermissions("Some permitted workers do not exist")
    return list(workers)


def get_request_fingerprint(payload: JobCreate) -> str:
    request = payload.model_dump(mode="json")
    request["permitted_user_ids"] = sorted(set(payload.permitted_user_ids))
    request["permitted_worker_ids"] = sorted(set(payload.permitted_worker_ids))
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_job(
    session: Session,
    user: User,
    payload: JobCreate,
    idempotency_key: str,
) -> Job:
    fingerprint = get_request_fingerprint(payload)
    stmt = select(Job).where(
        Job.idempotency_key == idempotency_key,
        Job.user_id == user.id,
    )
    saved = session.scalar(stmt)

    if saved is None:
        job = Job(
            user=user,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            job_type=payload.job_type,
            params=payload.params,
            permission_policy=payload.permission_policy,
            permitted_users=get_permitted_users(payload, session),
            permitted_workers=get_permitted_workers(payload, session),
        )
        session.add(job)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if getattr(exc.orig, "sqlstate", None) != "23505":
                raise
            # A competing submission may have committed the same creator/key.
            saved = session.scalar(stmt)
            if saved is None:
                raise
        else:
            session.refresh(job)
            return job

    if saved.request_fingerprint != fingerprint:
        raise JobCreationConflict("Conflicting create requests")
    return saved


def accessible_user_jobs_query(user: User):
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

def job_accessible_for_user(job: Job, user: User) -> bool:

    if job.permission_policy == PermissionPolicy.ALL:
        return True

    if job.user_id == user.id:
        return True

    if job.permission_policy in [PermissionPolicy.PERMITTED_USERS,
                                 PermissionPolicy.PERMITTED_WORKERS_AND_USERS]:
        return any(p_user.id == user.id for p_user in job.permitted_users)

    return False

def accessible_worker_jobs(worker: Worker):
    return select(Job).where(
        or_(
            Job.user_id == worker.user_id,
            Job.permission_policy == PermissionPolicy.ALL,
            and_(
                Job.permission_policy.in_(
                    [
                        PermissionPolicy.PERMITTED_USERS,
                        PermissionPolicy.PERMITTED_WORKERS_AND_USERS,
                    ]
                ),

                Job.permitted_users.any(User.id == worker.user_id),
            ),
            and_(
                Job.permission_policy.in_(
                    [
                        PermissionPolicy.PERMITTED_WORKERS,
                        PermissionPolicy.PERMITTED_WORKERS_AND_USERS,
                    ]
                ),
                Job.permitted_workers.any(Worker.id == worker.id),
            ),
        )
    )


def job_accessible_for_worker(job: Job, worker: Worker) -> bool:
    if job.permission_policy == PermissionPolicy.ALL:
        return True

    if job.user_id == worker.user_id:
        return True
    
    if job_accessible_for_user(job, worker.user):
        return True
    
    if job.permission_policy in [PermissionPolicy.PERMITTED_WORKERS, 
                                 PermissionPolicy.PERMITTED_WORKERS_AND_USERS]:
        return any(w.id == worker.id for w in job.permitted_workers)
    
    return False

def get_job(job_id: int, session: SessionDep, user: CurrentUser):
    stmt = accessible_user_jobs_query(user).where(Job.id == job_id)
    return session.scalar(stmt)
    
   
    
    
